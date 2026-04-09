import pytest
from unittest.mock import patch, MagicMock
from flask import json

# Import your Flask app module (adjust filename if needed)
import app as api


@pytest.fixture
def client():
    api.app.config['TESTING'] = True
    with api.app.test_client() as client:
        yield client


# -----------------------
# Health Endpoint
# -----------------------
@patch.object(api, 'cur')
@patch.object(api, 'databaseConnection')
def test_health_ok(mock_db, mock_cur, client):
    mock_cur.execute.return_value = None

    response = client.get('/api/health')
    data = response.get_json()

    assert response.status_code == 200
    assert data['status'] == 'ok'


@patch.object(api, 'cur')
def test_health_error(mock_cur, client):
    mock_cur.execute.side_effect = Exception("DB error")

    response = client.get('/api/health')
    assert response.status_code == 500


# -----------------------
# Route Endpoint
# -----------------------
@patch.object(api, 'routeHelperFunctionInQueryDijkstraReplacement')
def test_get_route_success(mock_route_helper, client):
    mock_route_helper.return_value = [
        {
            'seq': 1,
            'node': 1,
            'edge': 1,
            'cost': 10,
            'edgeToNextNode_direction': 'N',
            'edgeToNextNode_fromNode': 1,
            'latitude': 32.0,
            'longitude': -97.0,
            'label': 'Start',
            'node_type': 'waypoint'
        },
        {
            'seq': 2,
            'node': 2,
            'edge': None,
            'cost': 0,
            'edgeToNextNode_direction': None,
            'edgeToNextNode_fromNode': None,
            'latitude': 32.001,
            'longitude': -97.001,
            'label': 'End',
            'node_type': 'waypoint'
        }
    ]

    response = client.get('/api/route?from_node=1&to_node=2')
    data = response.get_json()

    assert response.status_code == 200
    assert data['from_node'] == 1
    assert data['to_node'] == 2
    assert len(data['waypoints']) == 2


def test_get_route_missing_params(client):
    response = client.get('/api/route')
    assert response.status_code == 400


@patch.object(api, 'routeHelperFunctionInQueryDijkstraReplacement')
def test_get_route_not_found(mock_route_helper, client):
    mock_route_helper.return_value = []

    response = client.get('/api/route?from_node=1&to_node=2')
    assert response.status_code == 404


# -----------------------
# Nearest Node Endpoint
# -----------------------
@patch.object(api, 'cur')
@patch('app.NearestNodeFinder')
def test_nearest_node_success(mock_finder_cls, mock_cur, client):
    mock_cur.fetchall.return_value = [
        {'id': 1, 'lat': 32.0, 'lng': -97.0}
    ]
    mock_cur.fetchone.return_value = {
        'id': 1,
        'latitude': 32.0,
        'longitude': -97.0,
        'label': 'Node',
        'node_type': 'waypoint',
        'zone': 'public'
    }

    mock_finder = MagicMock()
    mock_finder.get_nearest_active_node.return_value = 0
    mock_finder_cls.return_value = mock_finder

    response = client.get('/api/nearest?lat=32&lng=-97')
    data = response.get_json()

    assert response.status_code == 200
    assert data['node_id'] == 1


def test_nearest_node_missing_params(client):
    response = client.get('/api/nearest')
    assert response.status_code == 400


# -----------------------
# Nodes Endpoint
# -----------------------
@patch.object(api, 'cur')
def test_get_nodes(mock_cur, client):
    mock_cur.fetchall.return_value = [
        {'id': 1, 'latitude': 32, 'longitude': -97, 'label': 'A', 'node_type': 'gate'}
    ]

    response = client.get('/api/nodes')
    data = response.get_json()

    assert response.status_code == 200
    assert 'nodes' in data


# -----------------------
# Edges Endpoint
# -----------------------
@patch.object(api, 'cur')
def test_get_edges(mock_cur, client):
    mock_cur.fetchall.return_value = []

    response = client.get('/api/edges')
    assert response.status_code == 200


# -----------------------
# Amenities Endpoint
# -----------------------
@patch.object(api, 'cur')
def test_get_amenities(mock_cur, client):
    mock_cur.fetchall.return_value = []

    response = client.get('/api/amenities')
    assert response.status_code == 200


# -----------------------
# Random Node Endpoint
# -----------------------
@patch.object(api, 'cur')
def test_random_node_success(mock_cur, client):
    mock_cur.fetchone.return_value = {
        'node_id': 1,
        'latitude': 32,
        'longitude': -97,
        'zone': 'public'
    }

    response = client.get('/api/random-node?zone=public')
    assert response.status_code == 200


def test_random_node_invalid_zone(client):
    response = client.get('/api/random-node?zone=invalid')
    assert response.status_code == 400


# -----------------------
# Amenity Types Endpoint
# -----------------------
@patch.object(api, 'cur')
def test_get_amenity_types(mock_cur, client):
    mock_cur.fetchall.return_value = [{'type': 'restroom'}]

    response = client.get('/api/amenity-types')
    data = response.get_json()

    assert response.status_code == 200
    assert 'amenity_types' in data


# -----------------------
# Route to Amenity Endpoint
# -----------------------
@patch.object(api, 'routeHelperFunctionInQueryDijkstraReplacement')
@patch.object(api, 'cur')
def test_route_to_amenity_success(mock_cur, mock_route_helper, client):
    # Mock start node
    mock_cur.fetchone.side_effect = [
        {'lat': 32, 'lng': -97, 'zone': 'public'}
    ]

    mock_cur.fetchall.return_value = [
        {
            'amenity_id': 1,
            'nodeid': 2,
            'name': 'Restroom',
            'type': 'restroom',
            'latitude': 32,
            'longitude': -97,
            'node_lat': 32,
            'node_lng': -97,
            'node_zone': 'public'
        }
    ]

    mock_route_helper.return_value = [
        {
            'seq': 1,
            'node': 1,
            'edge': None,
            'cost': 0,
            'edgeToNextNode_direction': None,
            'edgeToNextNode_fromNode': None,
            'latitude': 32,
            'longitude': -97,
            'label': '',
            'node_type': 'waypoint'
        }
    ]

    response = client.get('/api/route-to-amenity?from_node=1&amenity_type=restroom')
    assert response.status_code == 200


def test_route_to_amenity_missing_params(client):
    response = client.get('/api/route-to-amenity')
    assert response.status_code == 400