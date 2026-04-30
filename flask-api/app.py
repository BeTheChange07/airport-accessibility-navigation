"""Flask backend for DFW Terminal D turn-by-turn navigation."""

import os
import math
import socket
import functools
import secrets
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from flask import (
    Flask, jsonify, request, send_from_directory, render_template_string,
    redirect, g,
)
from flask_cors import CORS
import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor, Json

import atexit
from NearestNodeFinder import NearestNodeFinder
from typing import Any

app = Flask(__name__)
CORS(app)

load_dotenv()

DB_CONFIG = {
    'host': os.environ.get('DB_HOST'),
    'port': os.environ.get('DB_PORT', '5432'),
    'dbname': os.environ.get('DB_NAME'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
}

databaseConnection = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
cur = databaseConnection.cursor()

def exitHandler():
    cur.close()
    databaseConnection.close()

atexit.register(exitHandler)


def _reopen_db_connection():
    """Replace the module-level connection + cursor with a fresh pair.

    Called when the existing connection has been closed by the server (AWS
    RDS idle timeout, network blip, etc.). Endpoints look up `cur` /
    `databaseConnection` via Python's module globals at call time, so
    rebinding here makes every subsequent request use the new connection
    without changing any of the route handlers.
    """
    global databaseConnection, cur
    try:
        databaseConnection.close()
    except Exception:
        pass
    databaseConnection = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cur = databaseConnection.cursor()


@app.before_request
def _ensure_db_alive():
    """Probe the DB connection before every request; reconnect if dead.

    The original code opened a single global connection at import time and
    never reopened it, so an RDS idle-timeout disconnect (or any transient
    network failure) would leave every subsequent request 500'ing with
    `psycopg2.InterfaceError: connection already closed` until Flask was
    restarted. The probe is a `SELECT 1` on a short-lived cursor — cheap
    enough to run on every request, and it both detects a closed connection
    and clears any "current transaction is aborted" state from a prior
    failed query.
    """
    global databaseConnection
    try:
        if databaseConnection.closed != 0:
            raise psycopg2.InterfaceError("connection marked closed")
        with databaseConnection.cursor() as probe:
            probe.execute("SELECT 1")
            probe.fetchone()
    except (psycopg2.InterfaceError, psycopg2.OperationalError):
        _reopen_db_connection()
    except psycopg2.Error:
        # Some other DB error (e.g., InFailedSqlTransaction) — rollback so
        # the connection becomes usable again rather than wedging on every
        # subsequent request.
        try:
            databaseConnection.rollback()
        except Exception:
            _reopen_db_connection()

def calculate_bearing(lat1, lng1, lat2, lng2):
    """Calculate bearing in degrees from north between two lat/lng points."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlng = math.radians(lng2 - lng1)
    x = math.sin(dlng) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlng)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def bearing_to_cardinal(bearing):
    """Convert a bearing in degrees to an 8-point cardinal direction label."""
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    index = round(bearing / 45) % 8
    return directions[index]


# Derives an amenity's real zone from its waypoint neighbors, since some
# linker nodes have a stale stored zone. Drop these into any query whose
# FROM is `amenities a LEFT JOIN nav_nodes n ON n.id = a.nodeid`.
AMENITY_DERIVED_ZONE_JOIN = """
LEFT JOIN LATERAL (
    SELECT SUM(CASE WHEN n2.zone = 'secure' THEN 1 ELSE 0 END) AS secure_n,
           SUM(CASE WHEN n2.zone = 'public' THEN 1 ELSE 0 END) AS public_n
    FROM nav_edges e
    JOIN nav_nodes n2
      ON n2.id = CASE WHEN e.from_node = a.nodeid THEN e.to_node ELSE e.from_node END
    WHERE (e.from_node = a.nodeid OR e.to_node = a.nodeid)
      AND n2.node_type = 'waypoint'
) nbr ON TRUE
LEFT JOIN LATERAL (
    SELECT n3.zone AS nearest_zone
    FROM nav_nodes n3
    WHERE n3.node_type = 'waypoint'
      AND n3.lat IS NOT NULL AND n.lat IS NOT NULL
    ORDER BY ((n3.lat - n.lat) * (n3.lat - n.lat) +
              (n3.lng - n.lng) * (n3.lng - n.lng)) ASC
    LIMIT 1
) nearest ON TRUE
"""
AMENITY_DERIVED_ZONE_EXPR = """
CASE
    WHEN COALESCE(nbr.secure_n, 0) > COALESCE(nbr.public_n, 0) THEN 'secure'
    WHEN COALESCE(nbr.public_n, 0) > COALESCE(nbr.secure_n, 0) THEN 'public'
    ELSE COALESCE(nearest.nearest_zone, n.zone, 'public')
END
"""


def haversine_distance_meters(lat1, lng1, lat2, lng2):
    """Calculate distance between two lat/lng points in meters using the haversine formula."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_direction_instruction(from_node, to_node, prev_direction, current_direction):
    """Generate a human-readable turn instruction."""
    if prev_direction is None:
        return f"Head {current_direction}"

    dir_to_deg = {
        'N': 0, 'NE': 45, 'E': 90, 'SE': 135,
        'S': 180, 'SW': 225, 'W': 270, 'NW': 315
    }

    if prev_direction in dir_to_deg and current_direction in dir_to_deg:
        diff = (dir_to_deg[current_direction] - dir_to_deg[prev_direction] + 360) % 360

        if diff == 0:
            return "Continue straight"
        elif diff <= 45:
            return "Slight right"
        elif diff <= 135:
            return "Turn right"
        elif diff <= 180:
            return "Turn around"
        elif diff <= 225:
            return "Turn around"
        elif diff <= 315:
            return "Turn left"
        else:
            return "Slight left"

    return "Continue"


@app.route('/')
def root():
    """Landing page: send visitors straight to the admin hub."""
    return redirect('/admin', code=302)


@app.route('/map')
def serve_map():
    """Serve the debug map visualization page with API key injected."""
    with open(os.path.join(os.path.dirname(__file__), 'map_debug.html'), 'r') as f:
        html = f.read()
    api_key = os.environ.get('MAPS_API_KEY', '')
    html = html.replace('{{MAPS_API_KEY}}', api_key)
    return html


@app.route('/calibrate')
def serve_calibrate():
    """Serve the node calibration tool with API key injected."""
    with open(os.path.join(os.path.dirname(__file__), 'calibrate_nodes.html'), 'r') as f:
        html = f.read()
    api_key = os.environ.get('MAPS_API_KEY', '')
    html = html.replace('{{MAPS_API_KEY}}', api_key)
    return html


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    try:
        cur.execute("SELECT 1")
        return jsonify({'status': 'ok', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


def routeHelperFunctionInQueryDijkstraReplacement(fromNode: int, toNode: int) -> list[dict[str, Any]]:
    # TODO: replace pgr_dijkstra with A*.
    # UC8: skip edges and nodes the admin has marked closed. The inner SQL
    # is the literal string pgr_dijkstra runs as its graph definition --
    # joining nav_edges to nav_nodes on both endpoints lets us drop edges
    # whose source / target was painted closed. COALESCE(.., false) keeps
    # this safe against rows that pre-date the iteration_3 migration.
    cur.execute("""
        SELECT
            r.node
        FROM pgr_dijkstra(
            'SELECT e.id, e.from_node AS source, e.to_node AS target, e.distance AS cost, e.distance AS reverse_cost FROM nav_edges e JOIN nav_nodes nf ON nf.id = e.from_node JOIN nav_nodes nt ON nt.id = e.to_node WHERE COALESCE(e.is_closed, false) = false AND COALESCE(nf.is_closed, false) = false AND COALESCE(nt.is_closed, false) = false',
            %s, %s,
            directed => false
        ) AS r
        ORDER BY r.seq
    """, (fromNode, toNode))
    node_ids = [row['node'] for row in cur.fetchall()]

    cur.execute("""
        WITH path_nodes AS (
            SELECT node_id, seq
            FROM unnest(%s::int[]) WITH ORDINALITY AS t(node_id, seq)
        ),
        path_pairs AS (
            SELECT
                pn.seq,
                pn.node_id AS node,
                pn_next.node_id AS next_node
            FROM path_nodes pn
            LEFT JOIN path_nodes pn_next ON pn_next.seq = pn.seq + 1
        ),
        path_edges AS (
            SELECT
                pp.seq,
                pp.node,
                e.id AS edge,
                e.distance AS cost,
                e.direction,
                e.from_node
            FROM path_pairs pp
            LEFT JOIN nav_edges e
                ON (e.from_node = pp.node AND e.to_node = pp.next_node)
                OR (e.to_node = pp.node AND e.from_node = pp.next_node)
        )
        SELECT
            pn.seq,
            pn.node_id AS node,
            pe.edge,
            COALESCE(pe.cost, 0) AS cost,
            pe.direction AS \"edgeToNextNode_direction\",
            pe.from_node AS \"edgeToNextNode_fromNode\",
            n.lat AS latitude,
            n.lng AS longitude,
            n.label,
            n.node_type
        FROM path_nodes pn
        LEFT JOIN path_edges pe ON pe.seq = pn.seq
        JOIN nav_nodes n ON n.id = pn.node_id
        ORDER BY pn.seq;
    """, (node_ids,))
    return cur.fetchall()
    
@app.route('/api/route', methods=['GET'])
def get_route():
    """Get navigation route between two nodes."""
    from_node = request.args.get('from_node', type=int)
    to_node = request.args.get('to_node', type=int)

    if not from_node or not to_node:
        return jsonify({'error': 'from_node and to_node are required'}), 400

    try:
        rows = routeHelperFunctionInQueryDijkstraReplacement(from_node, to_node)

        if not rows:
            return jsonify({'error': 'No route found'}), 404

        waypoints = []
        prev_direction = None

        for i, row in enumerate(rows):
            bearing_to_next = None
            cardinal_label = None
            distance_meters = 0.0
            if i < len(rows) - 1:
                next_row = rows[i + 1]
                bearing_to_next = calculate_bearing(
                    row['latitude'], row['longitude'],
                    next_row['latitude'], next_row['longitude']
                )
                cardinal_label = bearing_to_cardinal(bearing_to_next)
                distance_meters = haversine_distance_meters(
                    row['latitude'], row['longitude'],
                    next_row['latitude'], next_row['longitude']
                )

            # Derive the leg's cardinal direction from the real lat/lng bearing
            # rather than the stored nav_edges.direction column, which was
            # populated by a buggy nav editor getDir() (canvas y-down vs
            # geographic y-up) and has N/S, NE/SE, NW/SW flipped. Using the
            # bearing keeps `instruction` consistent with `cardinal_direction`.
            current_direction = cardinal_label

            instruction = get_direction_instruction(
                row['node'],
                rows[i + 1]['node'] if i < len(rows) - 1 else None,
                prev_direction,
                current_direction
            ) if current_direction else ("You have arrived" if i == len(rows) - 1 else "Continue")

            waypoints.append({
                'seq': row['seq'],
                'node_id': row['node'],
                'latitude': row['latitude'],
                'longitude': row['longitude'],
                'label': row['label'] or '',
                'node_type': row['node_type'] or 'waypoint',
                'direction': current_direction,
                'instruction': instruction,
                'distance_to_next': row['cost'] if row['cost'] and row['cost'] > 0 else 0,
                'bearing_to_next': round(bearing_to_next, 2) if bearing_to_next is not None else None,
                'cardinal_direction': cardinal_label,
                'distance_meters': round(distance_meters, 2),
            })

            if current_direction:
                prev_direction = current_direction

        total_distance = sum(d.get("cost", 0) for d in rows)

        return jsonify({
            'from_node': from_node,
            'to_node': to_node,
            'total_distance': total_distance,
            'num_waypoints': len(waypoints),
            'waypoints': waypoints
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/nearest', methods=['GET'])
def nearest_node():
    """Find the nearest node to a lat/lng. Optional `zone` filter ('public' / 'secure')."""
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    zone_param = request.args.get('zone')

    if lat is None or lng is None:
        return jsonify({'error': 'lat and lng are required'}), 400

    try:
        # Cache one KDTree per zone filter so repeated calls are fast.
        if not hasattr(nearest_node, "finders"):
            nearest_node.finders = {}
            nearest_node.node_ids_by_key = {}

        cache_key = zone_param if zone_param else '__all__'

        if cache_key not in nearest_node.finders:
            # UC8: exclude admin-painted closed nodes so we don't snap the
            # user onto a node that's about to be unrouteable.
            if zone_param:
                cur.execute("""
                    SELECT DISTINCT n.id, n.lat, n.lng FROM nav_nodes n
                    WHERE EXISTS (SELECT 1 FROM nav_edges e WHERE e.from_node = n.id OR e.to_node = n.id)
                      AND COALESCE(n.zone, 'public') = %s
                      AND COALESCE(n.is_closed, false) = false
                """, (zone_param,))
            else:
                cur.execute("""
                    SELECT DISTINCT n.id, n.lat, n.lng FROM nav_nodes n
                    WHERE EXISTS (SELECT 1 FROM nav_edges e WHERE e.from_node = n.id OR e.to_node = n.id)
                      AND COALESCE(n.is_closed, false) = false
                """)
            nodes = cur.fetchall()
            if not nodes:
                return jsonify({'error': f'No nodes available for zone {zone_param}'}), 404
            coordinates = [(node['lat'], node['lng']) for node in nodes]
            nearest_node.finders[cache_key] = NearestNodeFinder(coordinates)
            nearest_node.node_ids_by_key[cache_key] = [node['id'] for node in nodes]

        nearest_index = nearest_node.finders[cache_key].get_nearest_active_node((lat, lng))
        nearest_node_id = nearest_node.node_ids_by_key[cache_key][nearest_index]

        print(f"nearest node id: {nearest_node_id} (zone filter: {zone_param or 'none'})")

        cur.execute("""
            SELECT id, lat AS latitude, lng AS longitude, label, node_type, zone
            FROM nav_nodes
            WHERE id = %s
            LIMIT 1
        """, (nearest_node_id,))
        print("executed rds query")

        node = cur.fetchone()

        print(node)

        if not node:
            return jsonify({'error': 'No nodes found'}), 404

        return jsonify({
            'node_id': node['id'],
            'latitude': node['latitude'],
            'longitude': node['longitude'],
            'label': node['label'] or '',
            'node_type': node['node_type'] or 'waypoint',
            'zone': node['zone'] or 'public',
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/nodes', methods=['GET'])
def get_nodes():
    """Get labeled nodes for the destination picker. Optional `type` and `zone` filters."""
    node_type = request.args.get('type')
    node_zone = request.args.get('zone')

    conditions = []
    params = []

    if node_type:
        conditions.append("node_type = %s")
        params.append(node_type)
    if node_zone:
        conditions.append("zone = %s")
        params.append(node_zone)
        
    try:
        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        # is_closed exposed for the admin map (UC8); default-false for any
        # caller that pre-dates the iteration_3 migration.
        cur.execute(f"""
            SELECT id, lat AS latitude, lng AS longitude, label, node_type,
                   COALESCE(is_closed, false) AS is_closed,
                   closed_reason, closed_effective_from
            FROM nav_nodes
            {where_clause}
            ORDER BY label
        """, params)

        nodes = cur.fetchall()
        
        return jsonify({'nodes': list(nodes)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/edges', methods=['GET'])
def get_edges():
    """Return all nav_edges for visualization."""
    try:
        c = databaseConnection.cursor()
        # is_closed surfaced so the admin map can paint closed edges red
        # (UC8). Default-false for older rows.
        c.execute("""
            SELECT e.id, e.from_node, e.to_node, e.distance, e.direction,
                   COALESCE(e.is_closed, false) AS is_closed,
                   e.closed_reason, e.closed_effective_from,
                   n1.lat AS from_lat, n1.lng AS from_lng,
                   n2.lat AS to_lat, n2.lng AS to_lng
            FROM nav_edges e
            JOIN nav_nodes n1 ON n1.id = e.from_node
            JOIN nav_nodes n2 ON n2.id = e.to_node
        """)
        edges = c.fetchall()
        c.close()
        return jsonify({'edges': list(edges)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/amenities', methods=['GET'])
def get_amenities():
    """Return all amenities. Includes `has_accessible_unit` for client-side filtering."""
    try:
        c = databaseConnection.cursor()
        # Use the linked nav_node lat/lng so markers and routing share one frame.
        c.execute(f"""
            SELECT a.id,
                   a.nodeid,
                   a.name,
                   a.type,
                   COALESCE(n.lat, a.latitude)  AS latitude,
                   COALESCE(n.lng, a.longitude) AS longitude,
                   a.status,
                   a.occupancy,
                   a.crowdlevel,
                   a.lastupdated,
                   a.wheelchairaccessible,
                   (LOWER(COALESCE(a.wheelchairaccessible, '')) = 'yes') AS has_accessible_unit,
                   {AMENITY_DERIVED_ZONE_EXPR} AS zone
            FROM amenities a
            LEFT JOIN nav_nodes n ON n.id = a.nodeid
            {AMENITY_DERIVED_ZONE_JOIN}
            ORDER BY a.type, a.name
        """)
        amenities = c.fetchall()
        c.close()
        return jsonify({'amenities': list(amenities)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/random-node', methods=['GET'])
def get_random_node():
    """Return a random walkable waypoint in the requested zone ('secure' or 'public').

    Skips waypoints whose stored zone disagrees with their neighbors, so the
    Android test buttons don't drop the user on the wrong side of TSA.
    """
    zone = request.args.get('zone', type=str)
    if zone not in ('secure', 'public'):
        return jsonify({'error': "zone must be 'secure' or 'public'"}), 400
    try:
        c = databaseConnection.cursor()
        c.execute("""
            SELECT n.id AS node_id,
                   n.lat AS latitude,
                   n.lng AS longitude,
                   n.zone
            FROM nav_nodes n
            LEFT JOIN LATERAL (
                SELECT SUM(CASE WHEN n2.zone = n.zone THEN 1 ELSE 0 END) AS same_n,
                       SUM(CASE WHEN n2.zone <> n.zone THEN 1 ELSE 0 END) AS diff_n
                FROM nav_edges e
                JOIN nav_nodes n2
                  ON n2.id = CASE WHEN e.from_node = n.id THEN e.to_node ELSE e.from_node END
                WHERE (e.from_node = n.id OR e.to_node = n.id)
                  AND n2.node_type = 'waypoint'
            ) nbr ON TRUE
            WHERE n.node_type = 'waypoint'
              AND n.zone = %s
              AND COALESCE(nbr.same_n, 0) >= COALESCE(nbr.diff_n, 0)
            ORDER BY random()
            LIMIT 1
        """, (zone,))
        row = c.fetchone()
        c.close()
        if not row:
            return jsonify({'error': f'No waypoint nodes found in zone {zone}'}), 404
        return jsonify(row)
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/amenity-types', methods=['GET'])
def get_amenity_types():
    """Return the distinct amenity categories available for destination selection."""
    try:
        cur.execute("""
            SELECT DISTINCT type
            FROM amenities
            WHERE type IS NOT NULL AND type != ''
            ORDER BY type
        """)
        types = [row['type'] for row in cur.fetchall()]
        return jsonify({'amenity_types': types})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/route-to-amenity', methods=['GET'])
def route_to_amenity():
    """Find the nearest amenity of a given type to the starting node and return the route."""
    from_node = request.args.get('from_node', type=int)
    amenity_type = request.args.get('amenity_type', type=str)
    accessible_param = request.args.get('accessible', type=str)
    accessible = str(accessible_param).lower() in ('1', 'true', 'yes') if accessible_param else False

    if from_node is None or not amenity_type:
        return jsonify({'error': 'from_node and amenity_type are required'}), 400

    try:
        cur.execute("SELECT lat, lng, zone FROM nav_nodes WHERE id = %s", (from_node,))
        start = cur.fetchone()
        if not start:
            return jsonify({'error': 'Starting node not found'}), 404

        start_zone = start['zone'] or 'public'

        # Candidate filters shared by both branches:
        #   - zone match (same side of TSA as the user)
        #   - status must be active ('open' or 'busy') — admin-closed /
        #     under-maintenance amenities are not routable targets (UC7).
        #   - occupancy, if tracked, must not be 'full' — a filled restroom
        #     (UC5) is silently skipped so the user gets the next-nearest.
        #     Amenities that don't track occupancy (non-restrooms) have
        #     occupancy IS NULL and pass this filter.
        routable_status_filter = "a.status IN ('open', 'busy')"
        routable_occupancy_filter = "(a.occupancy IS NULL OR a.occupancy <> 'full')"

        if accessible:
            cur.execute(f"""
                SELECT a.id AS amenity_id, a.nodeID, a.name, a.type,
                       a.status, a.occupancy, a.crowdlevel,
                       a.latitude, a.longitude,
                       n.lat AS node_lat, n.lng AS node_lng,
                       {AMENITY_DERIVED_ZONE_EXPR} AS node_zone
                FROM amenities a
                JOIN nav_nodes n ON n.id = a.nodeID
                {AMENITY_DERIVED_ZONE_JOIN}
                WHERE a.type = %s
                  AND {AMENITY_DERIVED_ZONE_EXPR} = %s
                  AND LOWER(COALESCE(a.wheelchairaccessible, '')) = 'yes'
                  AND {routable_status_filter}
                  AND {routable_occupancy_filter}
            """, (amenity_type, start_zone))
            candidates = cur.fetchall()

            if not candidates:
                return jsonify({
                    'error': f'No accessible {amenity_type} reachable from your zone ({start_zone})'
                }), 404
        else:
            cur.execute(f"""
                SELECT a.id AS amenity_id, a.nodeID, a.name, a.type,
                       a.status, a.occupancy, a.crowdlevel,
                       a.latitude, a.longitude,
                       n.lat AS node_lat, n.lng AS node_lng,
                       {AMENITY_DERIVED_ZONE_EXPR} AS node_zone
                FROM amenities a
                JOIN nav_nodes n ON n.id = a.nodeID
                {AMENITY_DERIVED_ZONE_JOIN}
                WHERE a.type = %s
                  AND {AMENITY_DERIVED_ZONE_EXPR} = %s
                  AND {routable_status_filter}
                  AND {routable_occupancy_filter}
            """, (amenity_type, start_zone))
            candidates = cur.fetchall()

            if not candidates:
                return jsonify({
                    'error': f'No {amenity_type} amenities reachable from your zone ({start_zone})'
                }), 404

        # Sort by straight-line distance using the linked nav_node coords
        # so we stay in the same frame as routing.
        candidates.sort(key=lambda c: haversine_distance_meters(
            start['lat'], start['lng'], c['node_lat'], c['node_lng']
        ))

        # Try each candidate until one is routable.
        rows = None
        nearest = None
        target_node_id = None
        for candidate in candidates:
            target_node_id = candidate['nodeid']
            try:
                result = routeHelperFunctionInQueryDijkstraReplacement(from_node, target_node_id)
                if result:
                    rows = result
                    nearest = candidate
                    break
            except Exception:
                continue

        if not rows or not nearest:
            return jsonify({'error': 'No routable amenity of that type found'}), 404

        waypoints = []
        prev_direction = None

        for i, row in enumerate(rows):
            bearing_to_next = None
            cardinal_label = None
            distance_meters = 0.0
            if i < len(rows) - 1:
                next_row = rows[i + 1]
                bearing_to_next = calculate_bearing(
                    row['latitude'], row['longitude'],
                    next_row['latitude'], next_row['longitude']
                )
                cardinal_label = bearing_to_cardinal(bearing_to_next)
                distance_meters = haversine_distance_meters(
                    row['latitude'], row['longitude'],
                    next_row['latitude'], next_row['longitude']
                )

            # Derive the leg's cardinal direction from the real lat/lng bearing
            # rather than the stored nav_edges.direction column, which was
            # populated by a buggy nav editor getDir() (canvas y-down vs
            # geographic y-up) and has N/S, NE/SE, NW/SW flipped. Using the
            # bearing keeps `instruction` consistent with `cardinal_direction`.
            current_direction = cardinal_label

            instruction = get_direction_instruction(
                row['node'],
                rows[i + 1]['node'] if i < len(rows) - 1 else None,
                prev_direction,
                current_direction
            ) if current_direction else ("You have arrived" if i == len(rows) - 1 else "Continue")

            waypoints.append({
                'seq': row['seq'],
                'node_id': row['node'],
                'latitude': row['latitude'],
                'longitude': row['longitude'],
                'label': row['label'] or '',
                'node_type': row['node_type'] or 'waypoint',
                'direction': current_direction,
                'instruction': instruction,
                'distance_to_next': row['cost'] if row['cost'] and row['cost'] > 0 else 0,
                'bearing_to_next': round(bearing_to_next, 2) if bearing_to_next is not None else None,
                'cardinal_direction': cardinal_label,
                'distance_meters': round(distance_meters, 2),
            })

            if current_direction:
                prev_direction = current_direction

        total_distance = sum(d.get("cost", 0) for d in rows)

        return jsonify({
            'from_node': from_node,
            'to_node': target_node_id,
            'amenity_type': amenity_type,
            'destination_name': nearest['name'] or amenity_type,
            'destination_amenity_id': nearest['amenity_id'],
            'destination_status': nearest['status'],
            'destination_occupancy': nearest['occupancy'],
            'destination_crowdlevel': nearest['crowdlevel'],
            'total_distance': total_distance,
            'num_waypoints': len(waypoints),
            'waypoints': waypoints
        })

    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Admin portal (Iteration 2 / UC7)
#
# The admin portal is a small in-repo tool for staff. It's unauthenticated
# by design for the Iteration 2 demo — full login is UC4 (Iteration 3).
# ---------------------------------------------------------------------------

ADMIN_ALLOWED_STATUSES = ('open', 'busy', 'closed', 'maintenance', 'out_of_service')


def _serve_html(path, inject_maps_key=True):
    """Read an HTML file from disk and return it, optionally injecting the Maps key."""
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    if inject_maps_key:
        html = html.replace('{{MAPS_API_KEY}}', os.environ.get('MAPS_API_KEY', ''))
    return html


@app.route('/admin')
def admin_home():
    """Admin hub landing page with links to amenities, calibrate, map, nav editor."""
    path = os.path.join(os.path.dirname(__file__), 'templates', 'admin_home.html')
    return _serve_html(path, inject_maps_key=False)


@app.route('/admin/amenities')
def admin_amenities_page():
    """Amenity status + occupancy control page (UC7 + demo lever for UC5)."""
    path = os.path.join(os.path.dirname(__file__), 'templates', 'admin_amenities.html')
    return _serve_html(path, inject_maps_key=False)


@app.route('/admin/nav-editor')
def admin_nav_editor():
    """Serve the affine-transform nav editor from flask-api/templates/."""
    path = os.path.join(os.path.dirname(__file__), 'templates', 'nav_editor.html')
    return _serve_html(path, inject_maps_key=True)


@app.route('/admin/map')
def admin_map_page():
    """UC8 + UC7 admin surface: Google Maps basemap, node/edge paint mode,
    amenity click-to-toggle, and (UC3) reports list.
    """
    path = os.path.join(os.path.dirname(__file__), 'templates', 'admin_map.html')
    return _serve_html(path, inject_maps_key=True)


# UC8 paint endpoints. Production would gate these behind an admin role;
# for the prototype they reuse the unauthenticated admin surface pattern
# established by the Iteration 2 amenity status endpoints above.

def _paint_graph_elements(table: str, body: dict) -> tuple:
    """Shared bulk-paint helper for nav_nodes / nav_edges.

    Returns ``(json_payload, http_status)``. Validates the request body,
    runs the UPDATE in a fresh cursor, and stamps closed_effective_from /
    closed_reason atomically so rows never end up with a "closed but no
    timestamp" combination.
    """
    if table not in ('nav_nodes', 'nav_edges'):
        return {'error': 'invalid table'}, 500

    ids = body.get('ids')
    is_closed = body.get('is_closed')
    reason = body.get('reason')

    if not isinstance(ids, list) or len(ids) == 0:
        return {'error': 'ids must be a non-empty list of integer ids'}, 400
    if not all(isinstance(i, int) for i in ids):
        return {'error': 'ids must be a list of integers'}, 400
    if not isinstance(is_closed, bool):
        return {'error': 'is_closed must be true or false'}, 400

    try:
        c = databaseConnection.cursor()
        # When painting open we explicitly clear the reason / timestamp so
        # the row reads cleanly; when painting closed we stamp NOW() so
        # downstream tooling can see when the closure landed.
        c.execute(f"""
            UPDATE {table}
            SET is_closed = %s,
                closed_reason = CASE WHEN %s THEN %s ELSE NULL END,
                closed_effective_from = CASE WHEN %s THEN NOW() ELSE NULL END
            WHERE id = ANY(%s::int[])
            RETURNING id, is_closed, closed_reason, closed_effective_from
        """, (is_closed, is_closed, reason, is_closed, ids))
        rows = c.fetchall()
        databaseConnection.commit()
        c.close()
        return {'updated': len(rows), 'rows': list(rows)}, 200
    except Exception as e:
        databaseConnection.rollback()
        return {'error': str(e)}, 500


@app.route('/api/admin/nav/nodes/status', methods=['POST'])
def admin_paint_nodes_status():
    """UC8: bulk paint nav_nodes open or closed.

    Body: {"ids": [int, ...], "is_closed": bool, "reason": str?}
    """
    body = request.get_json(silent=True) or {}
    payload, status = _paint_graph_elements('nav_nodes', body)
    return jsonify(payload), status


@app.route('/api/admin/nav/edges/status', methods=['POST'])
def admin_paint_edges_status():
    """UC8: bulk paint nav_edges open or closed."""
    body = request.get_json(silent=True) or {}
    payload, status = _paint_graph_elements('nav_edges', body)
    return jsonify(payload), status


def _apply_amenity_status_change(amenity_id: int, new_status: str):
    """UC7 helper: bump an amenity's status and stamp lastupdated.

    Returns the updated row (RealDictCursor row) or ``None`` if the amenity
    doesn't exist or the status is rejected. Caller is responsible for
    commit/rollback; centralising the SQL here lets UC3's submit handler
    reuse the exact same write when a report category implies an OOS flip,
    so the two paths can never drift apart.
    """
    if new_status not in ADMIN_ALLOWED_STATUSES:
        return None
    c = databaseConnection.cursor()
    c.execute("""
        UPDATE amenities
        SET status = %s,
            lastupdated = NOW()
        WHERE id = %s
        RETURNING id, name, type, status, occupancy, crowdlevel, lastupdated
    """, (new_status, amenity_id))
    row = c.fetchone()
    c.close()
    return row


@app.route('/api/admin/amenity/<int:amenity_id>/status', methods=['POST'])
def admin_update_amenity_status(amenity_id):
    """UC7: set an amenity's status."""
    body = request.get_json(silent=True) or {}
    new_status = body.get('status')
    if new_status not in ADMIN_ALLOWED_STATUSES:
        return jsonify({
            'error': f'status must be one of {list(ADMIN_ALLOWED_STATUSES)}'
        }), 400

    try:
        row = _apply_amenity_status_change(amenity_id, new_status)
        databaseConnection.commit()
        if not row:
            return jsonify({'error': f'Amenity {amenity_id} not found'}), 404
        return jsonify(row)
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


# Fraction of stalls that should be occupied for each admin bucket.
# Thresholds match occupancySensors.py so the sensor's next roll-up tick
# won't overwrite an admin-set bucket.
OCCUPANCY_STATE_FRACTIONS = {
    'empty':  0.0,
    'medium': 1 / 3,
    'high':   2 / 3,
    'full':   1.0,
}


@app.route('/api/admin/amenity/<int:amenity_id>/occupancy', methods=['POST'])
def admin_force_amenity_occupancy(amenity_id):
    """Demo-control lever: set a restroom's occupancy to empty / medium / high / full.

    Restrooms only. Flips a proportional number of amenityunits rows
    occupied (stalls 1..N TRUE, the rest FALSE, ordered by unitid) and sets
    the aggregate amenities.occupancy bucket to match. Because the stall
    count and bucket agree after this runs, the occupancySensors.py roll-up
    won't undo the change on its next tick.
    """
    body = request.get_json(silent=True) or {}
    state = body.get('state')
    if state not in OCCUPANCY_STATE_FRACTIONS:
        return jsonify({
            'error': f"state must be one of {sorted(OCCUPANCY_STATE_FRACTIONS)}"
        }), 400

    try:
        c = databaseConnection.cursor()
        c.execute("SELECT id, type FROM amenities WHERE id = %s", (amenity_id,))
        amenity_row = c.fetchone()
        if not amenity_row:
            c.close()
            return jsonify({'error': f'Amenity {amenity_id} not found'}), 404
        if amenity_row['type'] != 'restroom':
            c.close()
            return jsonify({
                'error': 'Occupancy control only applies to restrooms'
            }), 400

        # How many stalls does this restroom actually have? Derived instead
        # of hard-coded so a restroom seeded with something other than 6
        # still lines up with the bucket thresholds.
        c.execute(
            "SELECT COUNT(*) AS total FROM amenityunits WHERE amenityid = %s",
            (amenity_id,),
        )
        total_row = c.fetchone() or {}
        total_stalls = total_row.get('total', 0) or 0
        n_occupied = round(total_stalls * OCCUPANCY_STATE_FRACTIONS[state])

        # Stalls 1..n_occupied become occupied, the rest vacant. One UPDATE
        # touches every row so lastupdated reflects the whole batch.
        c.execute("""
            UPDATE amenityunits
            SET occupied = (unitid <= %s),
                lastupdated = NOW()
            WHERE amenityid = %s
        """, (n_occupied, amenity_id))

        c.execute("""
            UPDATE amenities
            SET occupancy = %s,
                lastupdated = NOW()
            WHERE id = %s
            RETURNING id, name, type, status, occupancy, crowdlevel, lastupdated
        """, (state, amenity_id))
        row = c.fetchone()
        databaseConnection.commit()
        c.close()
        return jsonify(row)
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Auth (UC4 — Manage Account)
#
# Simple opaque-token model: random hex token, 7-day expiration, no refresh.
# Logout deletes the token row. Locked decision per the iteration plan; do
# not bolt on roles or refresh tokens here.
# ---------------------------------------------------------------------------

AUTH_TOKEN_TTL_DAYS = 7
USERNAME_MAX_LEN = 64
PASSWORD_MIN_LEN = 6


def _hash_password(plain: str) -> str:
    """bcrypt-hash a plaintext password. Returns the encoded hash string."""
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt verify. Returns False on any malformed input."""
    if not isinstance(hashed, str) or not isinstance(plain, str):
        return False
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def _new_auth_token():
    """Return a fresh ``(token, expires_at)`` pair."""
    token = secrets.token_hex(32)
    expires = datetime.now(timezone.utc) + timedelta(days=AUTH_TOKEN_TTL_DAYS)
    return token, expires


def _serialize_user(row):
    """Pick the public-safe subset of a users row for API responses."""
    if row is None:
        return None
    return {
        'id': row['id'],
        'username': row['username'],
        'name': row.get('name'),
        'accessibility_prefs': row.get('accessibility_prefs') or {},
        'filters': row.get('filters') or {},
        'profile': row.get('profile') or {},
        'created_at': row.get('created_at').isoformat()
            if row.get('created_at') and hasattr(row['created_at'], 'isoformat')
            else row.get('created_at'),
    }


def _current_user_optional():
    """Resolve the bearer token to a user row, or return None.

    Used both directly (for endpoints where auth is optional, e.g. UC3
    submit) and via ``_auth_required`` for the protected endpoints.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header[len('Bearer '):].strip()
    if not token:
        return None
    try:
        c = databaseConnection.cursor()
        c.execute("""
            SELECT u.id, u.username, u.name,
                   u.accessibility_prefs, u.filters, u.profile,
                   u.created_at
            FROM auth_tokens t
            JOIN users u ON u.id = t.user_id
            WHERE t.token = %s
              AND t.expires_at > NOW()
            LIMIT 1
        """, (token,))
        row = c.fetchone()
        c.close()
        return row
    except Exception:
        databaseConnection.rollback()
        return None


def _auth_required(view):
    """Decorator: 401 unless ``Authorization: Bearer <token>`` resolves."""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = _current_user_optional()
        if not user:
            return jsonify({'error': 'authentication required'}), 401
        g.current_user = user
        return view(*args, **kwargs)
    return wrapped


@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """UC4: create a new user and return an auth token.

    Body: {"username": str, "password": str, "name"?: str,
           "accessibility_prefs"?: object, "filters"?: object,
           "profile"?: object}
    """
    body = request.get_json(silent=True) or {}
    username = body.get('username')
    password = body.get('password')
    name = body.get('name')
    prefs = body.get('accessibility_prefs') or {}
    filters = body.get('filters') or {}
    profile = body.get('profile') or {}

    if not isinstance(username, str) or not (0 < len(username.strip()) <= USERNAME_MAX_LEN):
        return jsonify({'error': f'username must be 1..{USERNAME_MAX_LEN} chars'}), 400
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LEN:
        return jsonify({'error': f'password must be at least {PASSWORD_MIN_LEN} chars'}), 400
    for label, value in (('accessibility_prefs', prefs), ('filters', filters), ('profile', profile)):
        if not isinstance(value, dict):
            return jsonify({'error': f'{label} must be a JSON object'}), 400

    username = username.strip()
    try:
        c = databaseConnection.cursor()
        c.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if c.fetchone():
            c.close()
            return jsonify({'error': 'username already taken'}), 409

        c.execute("""
            INSERT INTO users (username, password_hash, name,
                               accessibility_prefs, filters, profile)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, username, name, accessibility_prefs, filters, profile,
                      created_at
        """, (
            username, _hash_password(password), name,
            Json(prefs), Json(filters), Json(profile),
        ))
        user = c.fetchone()

        token, expires = _new_auth_token()
        c.execute(
            "INSERT INTO auth_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user['id'], expires),
        )
        databaseConnection.commit()
        c.close()
        return jsonify({
            'token': token,
            'expires_at': expires.isoformat(),
            'user': _serialize_user(user),
        }), 201
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """UC4: verify credentials and issue a bearer token."""
    body = request.get_json(silent=True) or {}
    username = body.get('username')
    password = body.get('password')
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({'error': 'username and password are required'}), 400

    try:
        c = databaseConnection.cursor()
        c.execute("""
            SELECT id, username, password_hash, name,
                   accessibility_prefs, filters, profile, created_at
            FROM users
            WHERE username = %s
        """, (username.strip(),))
        user = c.fetchone()
        # Verify even when user is None to keep timing roughly equal.
        ok = _verify_password(password, user['password_hash']) if user else False
        if not user or not ok:
            c.close()
            return jsonify({'error': 'invalid username or password'}), 401

        token, expires = _new_auth_token()
        c.execute(
            "INSERT INTO auth_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user['id'], expires),
        )
        databaseConnection.commit()
        c.close()
        return jsonify({
            'token': token,
            'expires_at': expires.isoformat(),
            'user': _serialize_user(user),
        })
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
@_auth_required
def auth_logout():
    """UC4: delete the bearer token used on this request."""
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[len('Bearer '):].strip() if auth_header.startswith('Bearer ') else ''
    try:
        c = databaseConnection.cursor()
        c.execute("DELETE FROM auth_tokens WHERE token = %s", (token,))
        databaseConnection.commit()
        c.close()
        return jsonify({'status': 'logged_out'})
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/me', methods=['GET'])
@_auth_required
def me_get():
    """UC4: return the current user."""
    return jsonify({'user': _serialize_user(g.current_user)})


@app.route('/api/me', methods=['PUT'])
@_auth_required
def me_update():
    """UC4: partial update of name / accessibility_prefs / filters / profile."""
    body = request.get_json(silent=True) or {}
    user_id = g.current_user['id']

    sets = []
    params = []
    if 'name' in body:
        if body['name'] is not None and not isinstance(body['name'], str):
            return jsonify({'error': 'name must be a string or null'}), 400
        sets.append("name = %s")
        params.append(body['name'])
    for key in ('accessibility_prefs', 'filters', 'profile'):
        if key in body:
            if not isinstance(body[key], dict):
                return jsonify({'error': f'{key} must be a JSON object'}), 400
            sets.append(f"{key} = %s")
            params.append(Json(body[key]))

    if not sets:
        return jsonify({'error': 'no updatable fields supplied'}), 400

    params.append(user_id)
    try:
        c = databaseConnection.cursor()
        c.execute(f"""
            UPDATE users
            SET {", ".join(sets)}
            WHERE id = %s
            RETURNING id, username, name, accessibility_prefs, filters, profile,
                      created_at
        """, params)
        user = c.fetchone()
        databaseConnection.commit()
        c.close()
        return jsonify({'user': _serialize_user(user)})
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/me', methods=['DELETE'])
@_auth_required
def me_delete():
    """UC4: delete the current user. ON DELETE CASCADE clears auth_tokens."""
    user_id = g.current_user['id']
    try:
        c = databaseConnection.cursor()
        c.execute("DELETE FROM users WHERE id = %s", (user_id,))
        databaseConnection.commit()
        c.close()
        return jsonify({'status': 'deleted'})
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# UC3 — Submit User Report
#
# Report submission is auth-OPTIONAL: a guest can flag a broken restroom
# without signing in. list-mine requires auth; the admin list lives behind
# the unauthenticated admin surface (same pattern as UC7 for the prototype).
# ---------------------------------------------------------------------------

REPORT_ALLOWED_STATUSES = ('pending', 'in_progress', 'resolved', 'dismissed')
REPORT_ALLOWED_CATEGORIES = (
    'out_of_order', 'cleanliness', 'accessibility', 'wait_time', 'other',
)
# Categories that mean "this thing is broken right now". Submitting one of
# these flips the amenity to out_of_service via the existing UC7 path so
# routing stops sending users there. Kept tight on purpose: a "wait_time"
# report is loud user feedback, not a closure trigger.
REPORT_CATEGORIES_TRIGGER_OOS = {'out_of_order'}

REPORT_SUBMIT_THROTTLE_SECONDS = 60
# Per-process in-memory throttle, keyed by user_id (preferred) or IP.
# Process-local is fine for the prototype; production would push this into
# Redis so a horizontally-scaled deploy still rate-limits correctly.
_report_submit_last_seen: "dict[str, datetime]" = {}


@app.route('/api/reports', methods=['POST'])
def submit_report():
    """UC3: submit a new user report.

    Body: {amenity_id (int, required), category (req, in
    REPORT_ALLOWED_CATEGORIES), description?, rating? (1..5)}.
    """
    body = request.get_json(silent=True) or {}
    amenity_id = body.get('amenity_id')
    category = body.get('category')
    description = body.get('description')
    rating = body.get('rating')

    if not isinstance(amenity_id, int):
        return jsonify({'error': 'amenity_id (int) is required'}), 400
    if not isinstance(category, str) or category not in REPORT_ALLOWED_CATEGORIES:
        return jsonify({
            'error': f'category must be one of {list(REPORT_ALLOWED_CATEGORIES)}'
        }), 400
    if description is not None and not isinstance(description, str):
        return jsonify({'error': 'description must be a string or null'}), 400
    if rating is not None and (not isinstance(rating, int) or not 1 <= rating <= 5):
        return jsonify({'error': 'rating must be an integer 1..5'}), 400

    user = _current_user_optional()
    user_id = user['id'] if user else None
    submitter_ip = request.remote_addr or ''

    # Rate-limit: prefer user_id (logged-in), fall back to IP for guests.
    rate_key = f"u:{user_id}" if user_id else f"ip:{submitter_ip}"
    now = datetime.now(timezone.utc)
    last = _report_submit_last_seen.get(rate_key)
    if last is not None:
        elapsed = (now - last).total_seconds()
        if elapsed < REPORT_SUBMIT_THROTTLE_SECONDS:
            return jsonify({
                'error': 'Too many submissions. Please wait before reporting again.',
                'retry_after_seconds': int(REPORT_SUBMIT_THROTTLE_SECONDS - elapsed),
            }), 429
    _report_submit_last_seen[rate_key] = now

    try:
        c = databaseConnection.cursor()
        c.execute("""
            INSERT INTO user_reports
                (amenity_id, user_id, category, description, rating, submitter_ip)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, amenity_id, user_id, category, description, rating,
                      status, created_at, resolved_at
        """, (amenity_id, user_id, category, description, rating, submitter_ip))
        report = c.fetchone()
        databaseConnection.commit()
        c.close()

        # Category-driven UC7 flip. Best-effort: if the amenity update fails
        # we don't unwind the report -- the report still represents real
        # user feedback even if the status transition didn't take.
        if category in REPORT_CATEGORIES_TRIGGER_OOS:
            try:
                _apply_amenity_status_change(amenity_id, 'out_of_service')
                databaseConnection.commit()
            except Exception:
                databaseConnection.rollback()

        return jsonify({'report': dict(report)}), 201
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/reports/mine', methods=['GET'])
@_auth_required
def list_my_reports():
    """UC3: list the current user's reports, newest first."""
    user_id = g.current_user['id']
    try:
        c = databaseConnection.cursor()
        c.execute("""
            SELECT r.id, r.amenity_id,
                   a.name AS amenity_name, a.type AS amenity_type,
                   r.category, r.description, r.rating, r.status,
                   r.created_at, r.resolved_at
            FROM user_reports r
            LEFT JOIN amenities a ON a.id = r.amenity_id
            WHERE r.user_id = %s
            ORDER BY r.created_at DESC
        """, (user_id,))
        rows = c.fetchall()
        c.close()
        return jsonify({'reports': list(rows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/reports', methods=['GET'])
def admin_list_reports():
    """UC3 admin: list every report for the admin map panel.

    Same unauthenticated admin pattern as the existing UC7 endpoints.
    Production would gate behind an admin role.
    """
    try:
        c = databaseConnection.cursor()
        c.execute("""
            SELECT r.id, r.amenity_id,
                   a.name AS amenity_name, a.type AS amenity_type,
                   r.user_id, u.username,
                   r.category, r.description, r.rating, r.status,
                   r.created_at, r.resolved_at
            FROM user_reports r
            LEFT JOIN amenities a ON a.id = r.amenity_id
            LEFT JOIN users     u ON u.id = r.user_id
            ORDER BY
                CASE r.status
                    WHEN 'pending'     THEN 0
                    WHEN 'in_progress' THEN 1
                    ELSE 2
                END,
                r.created_at DESC
        """)
        rows = c.fetchall()
        c.close()
        return jsonify({'reports': list(rows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/reports/<int:report_id>/status', methods=['POST'])
def admin_update_report_status(report_id):
    """UC3 admin: change a report's status. Stamps resolved_at on resolve/dismiss."""
    body = request.get_json(silent=True) or {}
    new_status = body.get('status')
    if new_status not in REPORT_ALLOWED_STATUSES:
        return jsonify({
            'error': f'status must be one of {list(REPORT_ALLOWED_STATUSES)}'
        }), 400
    try:
        c = databaseConnection.cursor()
        c.execute("""
            UPDATE user_reports
            SET status = %s,
                resolved_at = CASE WHEN %s IN ('resolved', 'dismissed')
                                   THEN NOW() ELSE NULL END
            WHERE id = %s
            RETURNING id, amenity_id, user_id, category, description, rating,
                      status, created_at, resolved_at
        """, (new_status, new_status, report_id))
        row = c.fetchone()
        databaseConnection.commit()
        c.close()
        if not row:
            return jsonify({'error': f'report {report_id} not found'}), 404
        return jsonify({'report': dict(row)})
    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


def _detect_lan_ip():
    """Return the IP address Flask will advertise on the LAN.

    Honors the HOST_IP env var if set, otherwise uses the OS's outbound
    interface (same trick Flask/Werkzeug uses for its "Running on" line).
    Falls back to localhost if both paths fail.
    """
    configured = os.environ.get('HOST_IP')
    if configured:
        return configured
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # No packets are actually sent — just asks the OS which interface
            # would handle traffic to an arbitrary external address.
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


if __name__ == '__main__':
    # Print a visible reminder of the admin portal URL at startup. Guarded so
    # Flask's debug-mode reloader doesn't print it twice (once per process).
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        lan_ip = _detect_lan_ip()
        banner_lines = [
            "",
            "=" * 60,
            "  Admin portal:   http://127.0.0.1:5000/admin",
        ]
        if lan_ip and lan_ip != "127.0.0.1":
            banner_lines.append(f"  LAN:            http://{lan_ip}:5000/admin")
        banner_lines.append("  (Or just open the root URL — it redirects.)")
        banner_lines.append("=" * 60)
        banner_lines.append("")
        print("\n".join(banner_lines), flush=True)
    app.run(host='0.0.0.0', port=5000, debug=True)