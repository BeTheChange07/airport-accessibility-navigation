"""All Python tests for flask-api/app.py.

Section 1: Pure-helper unit tests (parameterized).
Section 2: Endpoint use-case tests via the Flask test client.

DB and NearestNodeFinder are stubbed in conftest.py — do not duplicate that here.
"""

from datetime import datetime, timezone

import bcrypt
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
        cur.queue_fetchall([])  # filtered candidate query
        cur.queue_fetchall([])  # unfiltered classification query
        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=gate")
        assert res.status_code == 404
        body = res.get_json()
        err = body["error"]
        assert "gate" in err.lower()
        assert "public" in err.lower()
        assert body["reason"] == "none_in_zone"


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
        cur.queue_fetchall([])  # filtered candidate query -> empty triggers 404
        cur.queue_fetchall([])  # unfiltered classification query
        client.get("/api/route-to-amenity?from_node=1&amenity_type=restroom")

        candidate_sql = next(
            (sql for sql, _ in cur.executed if sql and "amenity_id" in sql),
            None,
        )
        assert candidate_sql is not None, "Expected candidate SELECT to have run"
        assert "a.status IN ('open', 'busy')" in candidate_sql
        assert "a.occupancy IS NULL OR a.occupancy <> 'full'" in candidate_sql

    def test_all_closed_returns_specific_reason(self, client, cur):
        """When every restroom in zone is admin-closed, reason='all_closed'."""
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "secure"})
        cur.queue_fetchall([])  # filtered query — none routable
        cur.queue_fetchall([    # unfiltered — every row is exactly 'closed'
            {"status": "closed", "occupancy": "low"},
            {"status": "closed", "occupancy": "medium"},
            {"status": "closed", "occupancy": None},
        ])
        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=restroom")
        assert res.status_code == 404
        body = res.get_json()
        assert body["reason"] == "all_closed"
        assert "closed" in body["error"].lower()

    def test_all_full_returns_specific_reason(self, client, cur):
        """When every restroom is full but open, reason='all_full'."""
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "secure"})
        cur.queue_fetchall([])
        cur.queue_fetchall([
            {"status": "open", "occupancy": "full"},
            {"status": "busy", "occupancy": "full"},
        ])
        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=restroom")
        assert res.status_code == 404
        body = res.get_json()
        assert body["reason"] == "all_full"
        assert "full" in body["error"].lower()

    def test_unreachable_when_dijkstra_fails(self, client, cur):
        """Candidates exist but pgr_dijkstra cuts them off → reason='unreachable'."""
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "secure"})
        cur.queue_fetchall([self._candidate()])
        # Dijkstra returns nothing for both queries — unreachable.
        cur.queue_fetchall([])
        cur.queue_fetchall([])
        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=food")
        assert res.status_code == 404
        body = res.get_json()
        assert body["reason"] == "unreachable"

    @pytest.mark.parametrize("status,routable", [
        ("open", True),
        ("busy", True),
        ("closed", False),
        ("maintenance", False),
        ("out_of_service", False),
    ])
    def test_status_filter_for_each_dropdown_value(self, client, cur, status, routable):
        """Each admin dropdown value flows through the status filter as expected.

        open/busy survive `a.status IN ('open', 'busy')` and reach the
        dijkstra path. closed/maintenance/out_of_service get filtered out at
        the SQL level so the user never routes to them.
        """
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "secure"})
        if routable:
            cur.queue_fetchall([self._candidate(status=status)])
            cur.queue_fetchall([{"node": 1}, {"node": 42}])
            cur.queue_fetchall(self._dijkstra_rows())
            res = client.get("/api/route-to-amenity?from_node=1&amenity_type=food")
            assert res.status_code == 200, f"status={status!r} should be routable"
        else:
            # The candidate query returns empty (filtered out by status), so
            # the unfiltered classification query runs next — return that
            # single row so we can verify the reason.
            cur.queue_fetchall([])
            cur.queue_fetchall([{"status": status, "occupancy": None}])
            res = client.get("/api/route-to-amenity?from_node=1&amenity_type=food")
            assert res.status_code == 404, f"status={status!r} should be filtered"

    def test_classify_picks_specific_reason_per_status(self, client, cur):
        """All-maintenance and all-OOS get their own reasons, not 'all_closed'."""
        # All maintenance.
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "secure"})
        cur.queue_fetchall([])
        cur.queue_fetchall([
            {"status": "maintenance", "occupancy": None},
            {"status": "maintenance", "occupancy": None},
        ])
        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=restroom")
        assert res.get_json()["reason"] == "all_maintenance"

        cur.reset()
        # All out_of_service.
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "secure"})
        cur.queue_fetchall([])
        cur.queue_fetchall([
            {"status": "out_of_service", "occupancy": None},
            {"status": "out_of_service", "occupancy": None},
        ])
        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=restroom")
        assert res.get_json()["reason"] == "all_out_of_service"

        cur.reset()
        # Mixed unavailable status flavors → all_unavailable_status.
        cur.queue_fetchone({"lat": 32.9, "lng": -97.0, "zone": "secure"})
        cur.queue_fetchall([])
        cur.queue_fetchall([
            {"status": "closed", "occupancy": None},
            {"status": "maintenance", "occupancy": None},
            {"status": "out_of_service", "occupancy": None},
        ])
        res = client.get("/api/route-to-amenity?from_node=1&amenity_type=restroom")
        assert res.get_json()["reason"] == "all_unavailable_status"


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

    @pytest.mark.parametrize("status", [
        "open", "busy", "closed", "maintenance", "out_of_service",
    ])
    def test_each_dropdown_value_persists(self, client, cur, status):
        """Every value the admin dropdown can emit must round-trip cleanly.

        The admin select renders STATUS_OPTIONS verbatim. If any of those five
        ever gets rejected by the backend, the dropdown silently breaks for
        that one option — easy to miss because the others keep working. This
        test pins all five.
        """
        cur.queue_fetchone({
            "id": 5, "name": "D5 Restroom", "type": "restroom",
            "status": status, "occupancy": "low", "crowdlevel": 10,
            "lastupdated": "2026-04-18T11:00:00+00:00",
        })
        res = client.post("/api/admin/amenity/5/status", json={"status": status})
        assert res.status_code == 200, f"status={status!r} was rejected: {res.data!r}"
        assert res.get_json()["status"] == status

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


class TestUC8RoutingSkipsClosed:
    # Use case: UC8 (Update Infrastructure Status) -- routing endpoints
    # must skip nodes / edges the admin has painted closed.

    def test_dijkstra_inner_sql_filters_closed(self, client, cur):
        """/api/route's pgr_dijkstra graph-definition string excludes closed elements."""
        cur.queue_fetchall([{"node": 1}, {"node": 2}])
        cur.queue_fetchall([
            {
                "seq": 1, "node": 1, "edge": 10, "cost": 5.0,
                "edgeToNextNode_direction": "N",
                "edgeToNextNode_fromNode": 1,
                "latitude": 32.9, "longitude": -97.0,
                "label": "A", "node_type": "waypoint",
            },
            {
                "seq": 2, "node": 2, "edge": None, "cost": 0.0,
                "edgeToNextNode_direction": None,
                "edgeToNextNode_fromNode": None,
                "latitude": 32.9010, "longitude": -97.0,
                "label": "B", "node_type": "waypoint",
            },
        ])
        res = client.get("/api/route?from_node=1&to_node=2")
        assert res.status_code == 200
        # The first execute() call is the pgr_dijkstra invocation; its SQL
        # contains the inner graph-definition string we care about.
        dijkstra_sql = next(
            (sql for sql, _ in cur.executed if sql and "pgr_dijkstra" in sql),
            None,
        )
        assert dijkstra_sql is not None
        assert "COALESCE(e.is_closed, false) = false" in dijkstra_sql
        assert "COALESCE(nf.is_closed, false) = false" in dijkstra_sql
        assert "COALESCE(nt.is_closed, false) = false" in dijkstra_sql

    def test_nearest_excludes_closed_nodes(self, client, cur):
        """/api/nearest's candidate query filters is_closed = false."""
        cur.queue_fetchall([{"id": 7, "lat": 32.9, "lng": -97.0}])
        cur.queue_fetchone({
            "id": 7, "latitude": 32.9, "longitude": -97.0,
            "label": "Open Node", "node_type": "waypoint", "zone": "public",
        })
        res = client.get("/api/nearest?lat=32.9&lng=-97.0&zone=public")
        assert res.status_code == 200
        candidate_sql = next(
            (sql for sql, _ in cur.executed
             if sql and "FROM nav_nodes n" in sql and "EXISTS" in sql),
            None,
        )
        assert candidate_sql is not None
        assert "COALESCE(n.is_closed, false) = false" in candidate_sql


class TestUC8AdminPaintNodes:
    # Use case: UC8 paint nodes (POST /api/admin/nav/nodes/status).

    def test_happy_path(self, client, cur):
        """Happy path: paint two nodes closed, response echoes updated count."""
        cur.queue_fetchall([
            {"id": 1, "is_closed": True, "closed_reason": "flooding",
             "closed_effective_from": "2026-04-29T12:00:00+00:00"},
            {"id": 2, "is_closed": True, "closed_reason": "flooding",
             "closed_effective_from": "2026-04-29T12:00:00+00:00"},
        ])
        res = client.post(
            "/api/admin/nav/nodes/status",
            json={"ids": [1, 2], "is_closed": True, "reason": "flooding"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["updated"] == 2
        update_sql = next(
            (sql for sql, _ in cur.executed
             if sql and "UPDATE nav_nodes" in sql),
            None,
        )
        assert update_sql is not None
        # Sanity: closed_effective_from is stamped only when closing.
        assert "CASE WHEN %s THEN NOW() ELSE NULL END" in update_sql

    def test_empty_ids_returns_400(self, client):
        """Foot-gun: empty ids list rejected so a stray click can't close everything."""
        res = client.post(
            "/api/admin/nav/nodes/status",
            json={"ids": [], "is_closed": True},
        )
        assert res.status_code == 400

    def test_non_integer_ids_returns_400(self, client):
        """Foot-gun: non-integer ids rejected before hitting SQL."""
        res = client.post(
            "/api/admin/nav/nodes/status",
            json={"ids": ["DROP TABLE nav_nodes"], "is_closed": True},
        )
        assert res.status_code == 400

    def test_non_bool_is_closed_returns_400(self, client):
        """is_closed must be a real boolean; "true" string is not enough."""
        res = client.post(
            "/api/admin/nav/nodes/status",
            json={"ids": [1], "is_closed": "true"},
        )
        assert res.status_code == 400


class TestUC8AdminPaintEdges:
    # Use case: UC8 paint edges (POST /api/admin/nav/edges/status).

    def test_happy_path_paints_open(self, client, cur):
        """Painting open clears reason and effective_from on the SQL side."""
        cur.queue_fetchall([
            {"id": 9, "is_closed": False, "closed_reason": None,
             "closed_effective_from": None},
        ])
        res = client.post(
            "/api/admin/nav/edges/status",
            json={"ids": [9], "is_closed": False},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["updated"] == 1
        update_sql = next(
            (sql for sql, _ in cur.executed
             if sql and "UPDATE nav_edges" in sql),
            None,
        )
        assert update_sql is not None

    def test_empty_ids_returns_400(self, client):
        """Same foot-gun guard for edges."""
        res = client.post(
            "/api/admin/nav/edges/status",
            json={"ids": [], "is_closed": True},
        )
        assert res.status_code == 400


# ============================================================
# Section 3: UC4 — Manage Account
# ============================================================


def _user_row(**overrides):
    """Stand-in users row matching the columns the auth endpoints SELECT."""
    base = {
        "id": 1,
        "username": "user2",
        "name": "Test User",
        "accessibility_prefs": {},
        "filters": {},
        "profile": {},
        "created_at": datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


class TestUC4Register:
    # Use case: UC4 register (POST /api/auth/register).

    def test_happy_path(self, client, cur):
        """Register issues a token and returns the user."""
        cur.queue_fetchone(None)            # username uniqueness check
        cur.queue_fetchone(_user_row())     # INSERT ... RETURNING
        res = client.post(
            "/api/auth/register",
            json={"username": "user2", "password": "supersecret"},
        )
        assert res.status_code == 201
        body = res.get_json()
        assert "token" in body and len(body["token"]) >= 32
        assert body["user"]["username"] == "user2"
        # Auth token row INSERT actually ran.
        token_insert = next(
            (sql for sql, _ in cur.executed
             if sql and "INSERT INTO auth_tokens" in sql),
            None,
        )
        assert token_insert is not None

    def test_duplicate_username_returns_409(self, client, cur):
        """Duplicate username surfaces 409 instead of leaking the unique-violation."""
        cur.queue_fetchone({"?column?": 1})
        res = client.post(
            "/api/auth/register",
            json={"username": "user2", "password": "supersecret"},
        )
        assert res.status_code == 409

    def test_short_password_rejected(self, client):
        """Foot-gun: PASSWORD_MIN_LEN enforced at the boundary."""
        res = client.post(
            "/api/auth/register",
            json={"username": "user2", "password": "abc"},
        )
        assert res.status_code == 400


class TestUC4Login:
    # Use case: UC4 login (POST /api/auth/login).

    def test_happy_path(self, client, cur):
        """Correct password issues a fresh token."""
        password_hash = bcrypt.hashpw(b"supersecret", bcrypt.gensalt()).decode("utf-8")
        cur.queue_fetchone(_user_row(password_hash=password_hash))
        res = client.post(
            "/api/auth/login",
            json={"username": "user2", "password": "supersecret"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["user"]["username"] == "user2"
        assert "token" in body

    def test_bad_password_returns_401(self, client, cur):
        """Foot-gun: wrong password yields 401, not a leaky error."""
        password_hash = bcrypt.hashpw(b"supersecret", bcrypt.gensalt()).decode("utf-8")
        cur.queue_fetchone(_user_row(password_hash=password_hash))
        res = client.post(
            "/api/auth/login",
            json={"username": "user2", "password": "WRONG"},
        )
        assert res.status_code == 401

    def test_unknown_user_returns_401(self, client, cur):
        """Same opaque 401 when the user doesn't exist."""
        cur.queue_fetchone(None)
        res = client.post(
            "/api/auth/login",
            json={"username": "ghost", "password": "anything"},
        )
        assert res.status_code == 401


class TestUC4Me:
    # Use case: UC4 GET / PUT / DELETE /api/me, plus the auth middleware.

    def test_get_me_no_token_returns_401(self, client):
        """Foot-gun: no Authorization header is a hard 401."""
        res = client.get("/api/me")
        assert res.status_code == 401

    def test_get_me_bad_token_returns_401(self, client, cur):
        """Foot-gun: bogus / expired token yields 401 (token lookup returns None)."""
        # No fetchone queued -> default None -> token not found.
        res = client.get(
            "/api/me", headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert res.status_code == 401

    def test_get_me_happy_path(self, client, cur):
        """Bearer token resolves to the user row."""
        cur.queue_fetchone(_user_row())
        res = client.get(
            "/api/me", headers={"Authorization": "Bearer good-token"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["user"]["username"] == "user2"

    def test_put_me_updates_name(self, client, cur):
        """PUT /api/me updates and returns the patched row."""
        cur.queue_fetchone(_user_row())                       # auth lookup
        cur.queue_fetchone(_user_row(name="New Name"))        # UPDATE returning
        res = client.put(
            "/api/me",
            json={"name": "New Name"},
            headers={"Authorization": "Bearer good-token"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["user"]["name"] == "New Name"
        update_sql = next(
            (sql for sql, _ in cur.executed
             if sql and "UPDATE users" in sql),
            None,
        )
        assert update_sql is not None

    def test_put_me_empty_body_returns_400(self, client, cur):
        """Empty PUT body is rejected so we don't burn a no-op UPDATE."""
        cur.queue_fetchone(_user_row())
        res = client.put(
            "/api/me",
            json={},
            headers={"Authorization": "Bearer good-token"},
        )
        assert res.status_code == 400

    def test_delete_me(self, client, cur):
        """DELETE /api/me removes the user (auth_tokens cascades)."""
        cur.queue_fetchone(_user_row())  # auth lookup
        res = client.delete(
            "/api/me", headers={"Authorization": "Bearer good-token"},
        )
        assert res.status_code == 200
        delete_sql = next(
            (sql for sql, _ in cur.executed
             if sql and "DELETE FROM users" in sql),
            None,
        )
        assert delete_sql is not None


class TestUC4Logout:
    # Use case: UC4 logout (POST /api/auth/logout).
    def test_logout_deletes_token(self, client, cur):
        cur.queue_fetchone(_user_row())  # auth lookup
        res = client.post(
            "/api/auth/logout",
            headers={"Authorization": "Bearer good-token"},
        )
        assert res.status_code == 200
        delete_sql = next(
            (sql for sql, _ in cur.executed
             if sql and "DELETE FROM auth_tokens" in sql),
            None,
        )
        assert delete_sql is not None


# ============================================================
# Section 4: UC3 — Submit User Report
# ============================================================


def _report_row(**overrides):
    base = {
        "id": 1,
        "amenity_id": 5,
        "user_id": None,
        "category": "cleanliness",
        "description": "paper towels out",
        "rating": 3,
        "status": "pending",
        "created_at": datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc),
        "resolved_at": None,
    }
    base.update(overrides)
    return base


class TestUC3SubmitReport:
    # Use case: UC3 submit (POST /api/reports). Auth optional.

    def test_happy_path_as_guest(self, client, cur):
        """Guest report: user_id stays NULL, INSERT row echoed back."""
        cur.queue_fetchone(_report_row())
        res = client.post("/api/reports", json={
            "amenity_id": 5, "category": "cleanliness",
            "description": "paper towels out", "rating": 3,
        })
        assert res.status_code == 201
        body = res.get_json()
        assert body["report"]["id"] == 1
        assert body["report"]["user_id"] is None
        # Verify the INSERT executed.
        insert_sql = next(
            (sql for sql, _ in cur.executed
             if sql and "INSERT INTO user_reports" in sql),
            None,
        )
        assert insert_sql is not None

    def test_unknown_category_returns_400(self, client):
        """Foot-gun: a category outside the allow-list is rejected."""
        res = client.post("/api/reports", json={
            "amenity_id": 5, "category": "panic",
        })
        assert res.status_code == 400

    def test_missing_amenity_id_returns_400(self, client):
        """Foot-gun: amenity_id is required."""
        res = client.post("/api/reports", json={"category": "other"})
        assert res.status_code == 400

    def test_rating_out_of_range_returns_400(self, client):
        """Foot-gun: rating must be 1..5 if supplied."""
        res = client.post("/api/reports", json={
            "amenity_id": 5, "category": "other", "rating": 9,
        })
        assert res.status_code == 400

    def test_rate_limit_returns_429(self, client, cur):
        """Foot-gun: NFR 6.1 — second submit within 60s is throttled to 429."""
        cur.queue_fetchone(_report_row())
        first = client.post("/api/reports", json={
            "amenity_id": 5, "category": "other",
        })
        assert first.status_code == 201
        second = client.post("/api/reports", json={
            "amenity_id": 5, "category": "other",
        })
        assert second.status_code == 429
        assert "retry_after_seconds" in second.get_json()

    def test_out_of_order_triggers_amenity_status_change(self, client, cur):
        """Category 'out_of_order' reuses the UC7 path to flip the amenity."""
        cur.queue_fetchone(_report_row(category="out_of_order"))
        # UC7 helper UPDATE returns the new amenity row.
        cur.queue_fetchone({
            "id": 5, "name": "D5 Restroom", "type": "restroom",
            "status": "out_of_service", "occupancy": "low", "crowdlevel": 0,
            "lastupdated": datetime(2026, 4, 29, 12, 1, tzinfo=timezone.utc),
        })
        res = client.post("/api/reports", json={
            "amenity_id": 5, "category": "out_of_order",
        })
        assert res.status_code == 201
        amenity_update = next(
            (sql for sql, _ in cur.executed
             if sql and "UPDATE amenities" in sql and "status" in sql),
            None,
        )
        assert amenity_update is not None, (
            "Expected the UC7 _apply_amenity_status_change SQL to fire"
        )

    def test_logged_in_submit_attaches_user_id(self, client, cur):
        """When a valid bearer token resolves, user_id is recorded on the row."""
        cur.queue_fetchone(_user_row())                         # auth lookup
        cur.queue_fetchone(_report_row(user_id=1))              # INSERT RETURNING
        res = client.post(
            "/api/reports",
            json={"amenity_id": 5, "category": "wait_time"},
            headers={"Authorization": "Bearer good-token"},
        )
        assert res.status_code == 201
        # The INSERT params include user_id=1 (the auth lookup row's id).
        insert = next(
            ((sql, params) for sql, params in cur.executed
             if sql and "INSERT INTO user_reports" in sql),
            None,
        )
        assert insert is not None
        assert 1 in insert[1]


class TestUC3MyReports:
    # Use case: UC3 list-mine (GET /api/reports/mine). Auth required.

    def test_no_auth_returns_401(self, client):
        """Foot-gun: list-mine without a bearer token is a hard 401."""
        res = client.get("/api/reports/mine")
        assert res.status_code == 401

    def test_happy_path(self, client, cur):
        """Returns the user's reports newest-first with amenity name joined."""
        cur.queue_fetchone(_user_row())  # auth lookup
        cur.queue_fetchall([
            {
                "id": 9, "amenity_id": 5,
                "amenity_name": "D5 Restroom", "amenity_type": "restroom",
                "category": "cleanliness", "description": "wet floor",
                "rating": None, "status": "pending",
                "created_at": datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc),
                "resolved_at": None,
            }
        ])
        res = client.get(
            "/api/reports/mine",
            headers={"Authorization": "Bearer good-token"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert len(body["reports"]) == 1
        assert body["reports"][0]["amenity_name"] == "D5 Restroom"


class TestUC3AdminReports:
    # Use case: UC3 admin list / resolve.

    def test_admin_list_returns_rows(self, client, cur):
        cur.queue_fetchall([{
            "id": 1, "amenity_id": 5,
            "amenity_name": "D5 Restroom", "amenity_type": "restroom",
            "user_id": 1, "username": "user2",
            "category": "out_of_order", "description": None, "rating": None,
            "status": "pending",
            "created_at": datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc),
            "resolved_at": None,
        }])
        res = client.get("/api/admin/reports")
        assert res.status_code == 200
        assert res.get_json()["reports"][0]["username"] == "user2"

    def test_admin_resolve_happy_path(self, client, cur):
        """Resolving stamps resolved_at via the SQL CASE WHEN."""
        cur.queue_fetchone(_report_row(
            id=1, status="resolved",
            resolved_at=datetime(2026, 4, 29, 12, 1, tzinfo=timezone.utc),
        ))
        res = client.post(
            "/api/admin/reports/1/status",
            json={"status": "resolved"},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["report"]["status"] == "resolved"
        update_sql = next(
            (sql for sql, _ in cur.executed
             if sql and "UPDATE user_reports" in sql),
            None,
        )
        assert update_sql is not None
        assert "resolved_at" in update_sql

    def test_admin_resolve_invalid_status_returns_400(self, client):
        """Foot-gun: status outside the allow-list is rejected."""
        res = client.post(
            "/api/admin/reports/1/status",
            json={"status": "banana"},
        )
        assert res.status_code == 400

    def test_admin_resolve_unknown_id_returns_404(self, client, cur):
        """Foot-gun: nonexistent report id returns 404 (RETURNING -> None)."""
        # No queue_fetchone -> default None
        res = client.post(
            "/api/admin/reports/9999/status",
            json={"status": "resolved"},
        )
        assert res.status_code == 404
