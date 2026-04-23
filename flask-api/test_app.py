"""All Python tests for flask-api/app.py.

Section 1: Pure-helper unit tests (parameterized).
Section 2: Endpoint use-case tests via the Flask test client.

DB and NearestNodeFinder are stubbed in conftest.py — do not duplicate that here.
"""

import pytest

from app import (
    calculate_bearing,
    bearing_to_cardinal,
    haversine_distance_meters,
    get_direction_instruction,
)


# ============================================================
# Section 1: Helper unit tests
# ============================================================


class TestCalculateBearing:
    @pytest.mark.parametrize("lat1,lng1,lat2,lng2,expected", [
        (0.0, 0.0, 1.0, 0.0, 0.0),     # north
        (0.0, 0.0, 0.0, 1.0, 90.0),    # east
        (1.0, 0.0, 0.0, 0.0, 180.0),   # south
        (0.0, 0.0, 0.0, -1.0, 270.0),  # west
    ])
    def test_cardinals(self, lat1, lng1, lat2, lng2, expected):
        b = calculate_bearing(lat1, lng1, lat2, lng2)
        # Bearing wraps at 360, so 0 and 360 both mean "north".
        diff = min(abs(b - expected), abs(b - expected - 360), abs(b - expected + 360))
        assert diff < 0.01


class TestBearingToCardinal:
    def test_eight_cardinals_and_boundaries(self):
        assert bearing_to_cardinal(0) == "N"
        assert bearing_to_cardinal(45) == "NE"
        assert bearing_to_cardinal(90) == "E"
        assert bearing_to_cardinal(135) == "SE"
        assert bearing_to_cardinal(180) == "S"
        assert bearing_to_cardinal(225) == "SW"
        assert bearing_to_cardinal(270) == "W"
        assert bearing_to_cardinal(315) == "NW"
        # Boundary cases — round() uses banker's rounding so 22.5 → 22.
        assert bearing_to_cardinal(22) == "N"
        assert bearing_to_cardinal(23) == "NE"


class TestHaversine:
    def test_zero_distance(self):
        assert haversine_distance_meters(32.9, -97.0, 32.9, -97.0) == 0.0

    def test_one_degree_lat_approx_111km(self):
        d = haversine_distance_meters(0.0, 0.0, 1.0, 0.0)
        assert 110_000 < d < 112_000

    def test_symmetry(self):
        d1 = haversine_distance_meters(32.89, -97.04, 32.90, -97.05)
        d2 = haversine_distance_meters(32.90, -97.05, 32.89, -97.04)
        assert abs(d1 - d2) < 1e-6


class TestDirectionInstruction:
    @pytest.mark.parametrize("prev,curr,expected", [
        (None, "N", "Head N"),
        ("N", "N", "Continue straight"),
        ("N", "E", "Turn right"),
        ("N", "W", "Turn left"),
        ("N", "S", "Turn around"),
    ])
    def test_branches(self, prev, curr, expected):
        assert get_direction_instruction(1, 2, prev, curr) == expected


# ============================================================
# Section 2: Endpoint use-case tests
# ============================================================


class TestHealth:
    # Use case: Health check (GET /api/health)
    def test_ok(self, client, cur):
        """Health endpoint returns ok when SELECT 1 succeeds."""
        res = client.get("/api/health")
        assert res.status_code == 200
        body = res.get_json()
        assert body["status"] == "ok"
        assert body["database"] == "connected"

    def test_db_error_returns_500(self, client, cur, monkeypatch):
        """Health endpoint returns 500 when the DB call raises."""
        def boom(*a, **k):
            raise Exception("simulated DB failure")
        monkeypatch.setattr(cur, "execute", boom)
        res = client.get("/api/health")
        assert res.status_code == 500
        body = res.get_json()
        assert body["status"] == "error"


class TestViewMap:
    # Use case: View Map (GET /api/nodes)
    def test_get_nodes_returns_list(self, client, cur):
        """Map node feed works through Flask + DB."""
        cur.queue_fetchall([
            {"id": 1, "latitude": 32.9, "longitude": -97.0,
             "label": "Gate D5", "node_type": "gate"}
        ])
        res = client.get("/api/nodes")
        assert res.status_code == 200
        body = res.get_json()
        assert body["nodes"][0]["label"] == "Gate D5"


class TestReroute:
    # Use case: Reroute (GET /api/route)
    def test_happy_path_returns_waypoints_with_instructions(self, client, cur):
        """3-node path produces correct turn-by-turn instructions."""
        cur.queue_fetchall([{"node": 1}, {"node": 2}, {"node": 3}])
        cur.queue_fetchall([
            {
                "seq": 1, "node": 1, "edge": 10, "cost": 5.0,
                "edgeToNextNode_direction": "N",
                "edgeToNextNode_fromNode": 1,
                "latitude": 32.9000, "longitude": -97.0,
                "label": "A", "node_type": "waypoint",
            },
            {
                "seq": 2, "node": 2, "edge": 11, "cost": 5.0,
                "edgeToNextNode_direction": "E",
                "edgeToNextNode_fromNode": 2,
                "latitude": 32.9010, "longitude": -97.0,
                "label": "B", "node_type": "waypoint",
            },
            {
                "seq": 3, "node": 3, "edge": None, "cost": 0.0,
                "edgeToNextNode_direction": None,
                "edgeToNextNode_fromNode": None,
                "latitude": 32.9010, "longitude": -96.999,
                "label": "C", "node_type": "waypoint",
            },
        ])
        res = client.get("/api/route?from_node=1&to_node=3")
        assert res.status_code == 200
        body = res.get_json()
        assert body["num_waypoints"] == 3
        assert body["waypoints"][0]["instruction"] == "Head N"
        assert body["waypoints"][1]["instruction"] == "Turn right"
        assert body["waypoints"][2]["instruction"] == "You have arrived"

    def test_missing_params_returns_400(self, client):
        """/api/route returns 400 when from_node/to_node are missing."""
        res = client.get("/api/route")
        assert res.status_code == 400

    def test_unroutable_returns_404(self, client, cur):
        """/api/route returns 404 when pgr_dijkstra produces no path.

        No queueing needed: both fetchall calls fall through to FakeCursor's
        default empty-list return, so the helper yields no rows.
        """
        res = client.get("/api/route?from_node=1&to_node=2")
        assert res.status_code == 404


class TestViewAmenities:
    # Use case: View Amenities (GET /api/amenities)
    def test_get_amenities_returns_list(self, client, cur):
        """/api/amenities returns the linked nav_node lat/lng so markers and routing share one frame."""
        cur.queue_fetchall([
            {
                "id": 1, "nodeid": 42, "name": "Starbucks", "type": "food",
                "latitude": 32.9005, "longitude": -97.0005,
                "status": "open", "wheelchairaccessible": "yes",
                "has_accessible_unit": True, "zone": "secure",
                "occupancy": None, "crowdlevel": 0,
                "lastupdated": "2026-04-18T10:00:00+00:00",
            }
        ])
        res = client.get("/api/amenities")
        assert res.status_code == 200
        body = res.get_json()
        assert len(body["amenities"]) == 1
        a = body["amenities"][0]
        assert a["latitude"] == 32.9005
        assert a["longitude"] == -97.0005
        assert a["has_accessible_unit"] is True
        assert a["zone"] == "secure"

    def test_response_surfaces_iteration2_fields(self, client, cur):
        """/api/amenities exposes occupancy, crowdlevel, lastupdated (UC5 + UC6)."""
        cur.queue_fetchall([
            {
                "id": 9, "nodeid": 77, "name": "D5 Restroom", "type": "restroom",
                "latitude": 32.9, "longitude": -97.0,
                "status": "open", "wheelchairaccessible": "yes",
                "has_accessible_unit": True, "zone": "secure",
                "occupancy": "medium", "crowdlevel": 42,
                "lastupdated": "2026-04-18T10:30:00+00:00",
            }
        ])
        res = client.get("/api/amenities")
        assert res.status_code == 200
        a = res.get_json()["amenities"][0]
        assert a["occupancy"] == "medium"
        assert a["crowdlevel"] == 42
        assert a["lastupdated"] == "2026-04-18T10:30:00+00:00"


class TestVerifySecurityZoneAccess:
    # Use case: Verify Security Zone Access (/api/nearest, /api/route-to-amenity)
    def test_nearest_with_secure_zone_returns_secure_node(self, client, cur):
        """/api/nearest applies the zone filter so we don't snap across TSA."""
        cur.queue_fetchall([{"id": 42, "lat": 32.9, "lng": -97.0}])
        cur.queue_fetchone({
            "id": 42, "latitude": 32.9, "longitude": -97.0,
            "label": "G Secure", "node_type": "waypoint", "zone": "secure",
        })
        res = client.get("/api/nearest?lat=32.9&lng=-97.0&zone=secure")
        assert res.status_code == 200
        body = res.get_json()
        assert body["node_id"] == 42
        assert body["zone"] == "secure"
        # Confirm the zone-filtered SQL ran.
        any_zone_filter_sql = any(
            sql and "COALESCE(n.zone" in sql for sql, _ in cur.executed
        )
        assert any_zone_filter_sql

    def test_nearest_missing_params_returns_400(self, client):
        """/api/nearest returns 400 when lat/lng are missing."""
        res = client.get("/api/nearest")
        assert res.status_code == 400

    def test_no_amenities_in_zone_returns_404(self, client, cur):
        """/api/route-to-amenity scopes candidates to the start node's zone."""
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "public"})
        cur.queue_fetchall([])
        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=gate")
        assert res.status_code == 404
        err = res.get_json()["error"]
        assert "gate" in err
        assert "public" in err


class TestGenerateRouteToAmenity:
    # Use case: Generate Route to Amenity (GET /api/route-to-amenity)

    @staticmethod
    def _candidate(**overrides):
        base = {
            "amenity_id": 500,
            "nodeid": 42,
            "name": "Starbucks",
            "type": "food",
            "latitude": 32.9005,
            "longitude": -97.0005,
            "node_lat": 32.9005,
            "node_lng": -97.0005,
            "node_zone": "secure",
            "status": "open",
            "occupancy": None,
            "crowdlevel": 0,
        }
        base.update(overrides)
        return base

    @staticmethod
    def _dijkstra_rows():
        """Two-waypoint path from the dijkstra reconstruction query."""
        return [
            {
                "seq": 1, "node": 1, "edge": 10, "cost": 5.0,
                "edgeToNextNode_direction": "N",
                "edgeToNextNode_fromNode": 1,
                "latitude": 32.9, "longitude": -97.0,
                "label": "Start", "node_type": "waypoint",
            },
            {
                "seq": 2, "node": 42, "edge": None, "cost": 0.0,
                "edgeToNextNode_direction": None,
                "edgeToNextNode_fromNode": None,
                "latitude": 32.9005, "longitude": -97.0005,
                "label": "Starbucks", "node_type": "amenity",
            },
        ]

    def test_happy_path_returns_waypoints(self, client, cur):
        """Full route-to-amenity flow returns serialized waypoints."""
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "secure"})
        cur.queue_fetchall([self._candidate()])
        # The dijkstra helper runs 2 queries.
        cur.queue_fetchall([{"node": 1}, {"node": 42}])
        cur.queue_fetchall(self._dijkstra_rows())

        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=food")
        assert res.status_code == 200
        body = res.get_json()
        assert body["from_node"] == 1
        assert body["to_node"] == 42
        assert body["amenity_type"] == "food"
        assert body["destination_name"] == "Starbucks"
        assert body["num_waypoints"] == 2
        assert body["waypoints"][0]["node_id"] == 1
        assert body["waypoints"][1]["node_id"] == 42

    def test_missing_params_returns_400(self, client):
        """/api/route-to-amenity returns 400 when from_node/amenity_type are missing."""
        res = client.get("/api/route-to-amenity")
        assert res.status_code == 400

    def test_response_surfaces_destination_state(self, client, cur):
        """Route response echoes destination status / occupancy so the client can warn.

        Iteration 2: the Android VM stores destination_amenity_id +
        destination_status + destination_occupancy from this payload so the
        polling loop can detect mid-route changes.
        """
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "secure"})
        cur.queue_fetchall([self._candidate(
            amenity_id=77, type="restroom", name="D5 Restroom",
            status="open", occupancy="high", crowdlevel=55
        )])
        cur.queue_fetchall([{"node": 1}, {"node": 42}])
        cur.queue_fetchall(self._dijkstra_rows())

        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=restroom")
        assert res.status_code == 200
        body = res.get_json()
        assert body["destination_amenity_id"] == 77
        assert body["destination_status"] == "open"
        assert body["destination_occupancy"] == "high"
        assert body["destination_crowdlevel"] == 55

    def test_candidate_sql_filters_closed_and_full(self, client, cur):
        """Route-to-amenity SQL includes the UC7 status filter and UC5 occupancy filter."""
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "public"})
        cur.queue_fetchall([])  # no candidates -> 404
        client.get("/api/route-to-amenity?from_node=1&amenity_type=restroom")

        candidate_sql = next(
            (sql for sql, _ in cur.executed if sql and "amenity_id" in sql),
            None,
        )
        assert candidate_sql is not None, "Expected candidate SELECT to have run"
        assert "a.status IN ('open', 'busy')" in candidate_sql
        assert "a.occupancy IS NULL OR a.occupancy <> 'full'" in candidate_sql


class TestAdminEndpoints:
    # Use case: UC7 (Update Amenity Status) + UC5 admin occupancy demo lever.
    # Iteration 2 admin portal is unauthenticated by design (UC4 login is Iteration 3).

    def test_set_status_happy_path(self, client, cur):
        """POST updates the status and returns the updated row."""
        cur.queue_fetchone({
            "id": 5, "name": "D5 Restroom", "type": "restroom",
            "status": "closed", "occupancy": "low", "crowdlevel": 10,
            "lastupdated": "2026-04-18T11:00:00+00:00",
        })
        res = client.post(
            "/api/admin/amenity/5/status",
            json={"status": "closed"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["status"] == "closed"
        # Confirm the UPDATE actually ran.
        update_sql = next(
            (sql for sql, _ in cur.executed if sql and "UPDATE amenities" in sql),
            None,
        )
        assert update_sql is not None
        assert "status = %s" in update_sql

    def test_set_status_rejects_unknown_value(self, client):
        """Status outside the allowed set yields 400."""
        res = client.post(
            "/api/admin/amenity/5/status",
            json={"status": "on_fire"},
        )
        assert res.status_code == 400

    def test_set_occupancy_full_happy_path(self, client, cur):
        """Admin 'Mark full' locks all stalls and sets the amenity bucket."""
        # First fetchone: restroom type check.
        cur.queue_fetchone({"id": 5, "type": "restroom"})
        # Second fetchone: stall count (drives how many amenityunits rows
        # get flipped to occupied for partial states like medium / high).
        cur.queue_fetchone({"total": 6})
        # Third fetchone: RETURNING row after the bucket UPDATE.
        cur.queue_fetchone({
            "id": 5, "name": "D5 Restroom", "type": "restroom",
            "status": "open", "occupancy": "full", "crowdlevel": 10,
            "lastupdated": "2026-04-18T11:05:00+00:00",
        })
        res = client.post(
            "/api/admin/amenity/5/occupancy",
            json={"state": "full"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["occupancy"] == "full"
        # Confirm both the unit-level UPDATE and the aggregate UPDATE ran.
        units_update = next(
            (sql for sql, _ in cur.executed if sql and "UPDATE amenityunits" in sql),
            None,
        )
        amenity_update = next(
            (sql for sql, _ in cur.executed
             if sql and "UPDATE amenities" in sql and "occupancy" in sql),
            None,
        )
        assert units_update is not None
        assert amenity_update is not None

    def test_set_occupancy_rejects_non_restroom(self, client, cur):
        """Occupancy control is restroom-only (UC5 scope)."""
        cur.queue_fetchone({"id": 7, "type": "gate"})
        res = client.post(
            "/api/admin/amenity/7/occupancy",
            json={"state": "full"},
        )
        assert res.status_code == 400

    def test_set_occupancy_rejects_bad_state(self, client):
        """state must be one of empty / medium / high / full."""
        res = client.post(
            "/api/admin/amenity/5/occupancy",
            json={"state": "bogus"},
        )
        assert res.status_code == 400


class TestRandomNode:
    # Use case: Random Node (GET /api/random-node)
    def test_success(self, client, cur):
        """/api/random-node returns the random waypoint row for the requested zone."""
        cur.queue_fetchone({
            "node_id": 7,
            "latitude": 32.9,
            "longitude": -97.0,
            "zone": "public",
        })
        res = client.get("/api/random-node?zone=public")
        assert res.status_code == 200
        body = res.get_json()
        assert body["node_id"] == 7
        assert body["zone"] == "public"

    def test_invalid_zone_returns_400(self, client):
        """/api/random-node rejects zones outside ('secure', 'public')."""
        res = client.get("/api/random-node?zone=invalid")
        assert res.status_code == 400


class TestAmenityTypes:
    # Use case: List Amenity Types (GET /api/amenity-types)
    def test_returns_distinct_types(self, client, cur):
        """/api/amenity-types returns the distinct types from the DB."""
        cur.queue_fetchall([{"type": "food"}, {"type": "restroom"}])
        res = client.get("/api/amenity-types")
        assert res.status_code == 200
        body = res.get_json()
        assert body["amenity_types"] == ["food", "restroom"]
