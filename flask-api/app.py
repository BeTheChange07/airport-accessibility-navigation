"""
Terminal D Navigation API
Flask backend for DFW Terminal D turn-by-turn navigation
"""

import os
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

import atexit
from NearestNodeFinder import NearestNodeFinder
from typing import Any

app = Flask(__name__)
CORS(app)

load_dotenv()

# Database configuration
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

def get_direction_instruction(from_node, to_node, prev_direction, current_direction):
    """Generate a human-readable turn instruction."""
    if prev_direction is None:
        return f"Head {current_direction}"

    # Map directions to degrees
    dir_to_deg = {
        'N': 0, 'NE': 45, 'E': 90, 'SE': 135,
        'S': 180, 'SW': 225, 'W': 270, 'NW': 315
    }

    # Calculate turn angle
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


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    try:
        cur.execute("SELECT 1")
        return jsonify({'status': 'ok', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


def routeHelperFunctionInQueryDijkstraReplacement(fromNode: int, toNode: int) -> list[dict[str, Any]]:
    #temporarily reuse djikstra query to get nodes ids to test the latter part of the function
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
    
    
    
    
    #Once we have the list of nodes, this query returns all the columns that were previously returned by the pgr_djikstra query, since that's what the calling function expects.
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
                e.distance AS cost
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
            n.latitude,
            n.longitude,
            n.label,
            n.node_type,
            n.x,
            n.y
        FROM path_nodes pn
        LEFT JOIN path_edges pe ON pe.seq = pn.seq
        JOIN nav_nodes n ON n.id = pn.node_id
        ORDER BY pn.seq;
    """, (node_ids,))
    return cur.fetchall()
    
@app.route('/api/route', methods=['GET'])
def get_route():
    """
    Get navigation route between two nodes.

    Query params:
        from_node: starting node ID
        to_node: destination node ID

    Returns:
        JSON with ordered list of waypoints (lat, lng, direction, instruction)
    """
    from_node = request.args.get('from_node', type=int)
    to_node = request.args.get('to_node', type=int)

    if not from_node or not to_node:
        return jsonify({'error': 'from_node and to_node are required'}), 400

    try:
        rows = routeHelperFunctionInQueryDijkstraReplacement(from_node, to_node) 
        #Extracting just that ^ part so I can figure out the rest of this function later
        
        if not rows:
            return jsonify({'error': 'No route found'}), 404

        # Get edge directions for the path
        waypoints = []
        total_distance = 0
        prev_direction = None

        for i, row in enumerate(rows):
            # Look up the direction of the edge to the next node
            current_direction = None
            if i < len(rows) - 1:
                next_node = rows[i + 1]['node']
                cur.execute("""
                    SELECT direction FROM nav_edges
                    WHERE (from_node = %s AND to_node = %s)
                       OR (from_node = %s AND to_node = %s)
                    LIMIT 1
                """, (row['node'], next_node, next_node, row['node']))
                edge = cur.fetchone()
                if edge:
                    current_direction = edge['direction']
                    # If the edge is reversed, flip the direction
                    cur.execute("""
                        SELECT direction FROM nav_edges
                        WHERE from_node = %s AND to_node = %s
                        LIMIT 1
                    """, (row['node'], next_node))
                    forward_edge = cur.fetchone()
                    if forward_edge:
                        current_direction = forward_edge['direction']
                    else:
                        # Edge is stored in reverse, flip direction
                        opposite = {
                            'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E',
                            'NE': 'SW', 'SW': 'NE', 'NW': 'SE', 'SE': 'NW'
                        }
                        current_direction = opposite.get(current_direction, current_direction)

            instruction = get_direction_instruction(
                row['node'],
                rows[i + 1]['node'] if i < len(rows) - 1 else None,
                prev_direction,
                current_direction
            ) if current_direction else ("You have arrived" if i == len(rows) - 1 else "Continue")

            total_distance += row['cost'] if row['cost'] and row['cost'] > 0 else 0

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
            })

            if current_direction:
                prev_direction = current_direction

        return jsonify({
            'from_node': from_node,
            'to_node': to_node,
            'total_distance': total_distance,
            'num_waypoints': len(waypoints),
            'waypoints': waypoints
        })

    except Exception as e:
        raise #This is just here for testing to effectively disable the except block so it will actually propogate the error up the chain for debugging
        return jsonify({'error': str(e)}), 500


@app.route('/api/nearest', methods=['GET'])
def nearest_node():
    """
    Find the nearest node to a given lat/lng (for GPS positioning).

    Query params:
        lat: latitude
        lng: longitude

    Returns:
        The closest node with its ID and other parameters.
    """
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)

    if lat is None or lng is None:
        return jsonify({'error': 'lat and lng are required'}), 400

    try:        
        if not hasattr(nearest_node, "finder"): 
            cur.execute("SELECT id, latitude, longitude FROM nav_nodes") #TODO, sprint 2, make sure to account for active/inactive mask
            nodes = cur.fetchall()
            coordinates = [(node['latitude'], node['longitude']) for node in nodes]
            nearest_node.nearestNodeFinderInstance = NearestNodeFinder(coordinates)
            nearest_node.nodeIDs = [node['id'] for node in nodes] #I am not trusting that the node IDs are 0 to N-1, so need to keep track of mapping from nearestNodeFinder's points array index to nodeID

        print("got to query")

        #Insert here query for node states and call nearestNodeFinderInstance.set_active_mask() before querying for nearest node, to ensure we are only returning active nodes
        nearest_index = nearest_node.nearestNodeFinderInstance.get_nearest_active_node((lat, lng))
        nearest_node_id = nearest_node.nodeIDs[nearest_index]

        print(f"nearest node id: {nearest_node_id}")

        cur.execute("""
            SELECT id, latitude, longitude, label, node_type
            FROM nav_nodes
            WHERE id = %s
            LIMIT 1
        """, (nearest_node_id, )) #Comma to make it a tuple and not just a parenthesized expression
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
        })

    except Exception as e:
        #raise #This is just here for testing to effectively disable the except block so it will actually propogate the error up the chain for debugging
        return jsonify({'error': str(e)}), 500
        

@app.route('/api/nodes', methods=['GET'])
def get_nodes():
    """
    Get all labeled nodes (gates, amenities, etc.) for the destination picker.

    Query params (optional):
        type: filter by node_type (e.g., 'gate', 'amenity', 'restroom')
    """
    node_type = request.args.get('type')

    try:
        if node_type:
            cur.execute("""
                SELECT id, latitude, longitude, label, node_type
                FROM nav_nodes
                WHERE node_type = %s AND label != ''
                ORDER BY label
            """, (node_type,))
        else:
            cur.execute("""
                SELECT id, latitude, longitude, label, node_type
                FROM nav_nodes
                WHERE label != ''
                ORDER BY node_type, label
            """)

        nodes = cur.fetchall()
        
        return jsonify({'nodes': list(nodes)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)