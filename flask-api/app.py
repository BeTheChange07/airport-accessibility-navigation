"""Flask backend for DFW Terminal D turn-by-turn navigation."""

import os
import math
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, render_template_string
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

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
    cur.execute("""
        SELECT
            r.node
        FROM pgr_dijkstra(
            'SELECT id, from_node AS source, to_node AS target, distance AS cost, distance AS reverse_cost FROM nav_edges',
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
            current_direction = None
            if i < len(rows) - 1 and row['edge'] is not None:
                current_direction = row['edgeToNextNode_direction']
                if row['edgeToNextNode_fromNode'] != row['node']:
                    # Edge stored in reverse, flip the direction.
                    opposite = {
                        'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E',
                        'NE': 'SW', 'SW': 'NE', 'NW': 'SE', 'SE': 'NW'
                    }
                    current_direction = opposite.get(current_direction, current_direction)

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
            if zone_param:
                cur.execute("""
                    SELECT DISTINCT n.id, n.lat, n.lng FROM nav_nodes n
                    WHERE EXISTS (SELECT 1 FROM nav_edges e WHERE e.from_node = n.id OR e.to_node = n.id)
                      AND COALESCE(n.zone, 'public') = %s
                """, (zone_param,))
            else:
                cur.execute("""
                    SELECT DISTINCT n.id, n.lat, n.lng FROM nav_nodes n
                    WHERE EXISTS (SELECT 1 FROM nav_edges e WHERE e.from_node = n.id OR e.to_node = n.id)
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
        cur.execute(f"""
            SELECT id, lat AS latitude, lng AS longitude, label, node_type
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
        c.execute("""
            SELECT e.id, e.from_node, e.to_node, e.distance, e.direction,
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

        # Only return amenities in the same zone as the user.
        if accessible:
            cur.execute(f"""
                SELECT a.id AS amenity_id, a.nodeID, a.name, a.type,
                       a.latitude, a.longitude,
                       n.lat AS node_lat, n.lng AS node_lng,
                       {AMENITY_DERIVED_ZONE_EXPR} AS node_zone
                FROM amenities a
                JOIN nav_nodes n ON n.id = a.nodeID
                {AMENITY_DERIVED_ZONE_JOIN}
                WHERE a.type = %s
                  AND {AMENITY_DERIVED_ZONE_EXPR} = %s
                  AND LOWER(COALESCE(a.wheelchairaccessible, '')) = 'yes'
            """, (amenity_type, start_zone))
            candidates = cur.fetchall()

            if not candidates:
                return jsonify({
                    'error': f'No accessible {amenity_type} reachable from your zone ({start_zone})'
                }), 404
        else:
            cur.execute(f"""
                SELECT a.id AS amenity_id, a.nodeID, a.name, a.type,
                       a.latitude, a.longitude,
                       n.lat AS node_lat, n.lng AS node_lng,
                       {AMENITY_DERIVED_ZONE_EXPR} AS node_zone
                FROM amenities a
                JOIN nav_nodes n ON n.id = a.nodeID
                {AMENITY_DERIVED_ZONE_JOIN}
                WHERE a.type = %s
                  AND {AMENITY_DERIVED_ZONE_EXPR} = %s
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
            current_direction = None
            if i < len(rows) - 1 and row['edge'] is not None:
                current_direction = row['edgeToNextNode_direction']
                if row['edgeToNextNode_fromNode'] != row['node']:
                    opposite = {
                        'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E',
                        'NE': 'SW', 'SW': 'NE', 'NW': 'SE', 'SE': 'NW'
                    }
                    current_direction = opposite.get(current_direction, current_direction)

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
            'total_distance': total_distance,
            'num_waypoints': len(waypoints),
            'waypoints': waypoints
        })

    except Exception as e:
        databaseConnection.rollback()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)