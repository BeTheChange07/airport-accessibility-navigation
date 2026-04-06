"""Unit tests for pure helper functions in app.py.

These tests do NOT touch the database — they only exercise math helpers.
Run with `pytest flask-api/test_app.py`.
"""

import math
import os
import sys

# Stub DB env vars and psycopg2.connect so importing app.py doesn't try to
# open a real connection.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")

import types  # noqa: E402

# Stub out NearestNodeFinder so we don't need numpy/scipy to import app.py
_fake_nnf_module = types.ModuleType("NearestNodeFinder")
class _FakeNNF:
    def __init__(self, *a, **kw): pass
    def get_nearest_active_node(self, *a, **kw): return 0
_fake_nnf_module.NearestNodeFinder = _FakeNNF  # type: ignore
sys.modules.setdefault("NearestNodeFinder", _fake_nnf_module)

import psycopg2  # noqa: E402

class _FakeCursor:
    def execute(self, *a, **kw): pass
    def fetchall(self): return []
    def fetchone(self): return None
    def close(self): pass

class _FakeConn:
    def cursor(self, *a, **kw): return _FakeCursor()
    def close(self): pass

psycopg2.connect = lambda *a, **kw: _FakeConn()  # type: ignore

sys.path.insert(0, os.path.dirname(__file__))
from app import (  # noqa: E402
    calculate_bearing,
    bearing_to_cardinal,
    haversine_distance_meters,
    get_direction_instruction,
)


def test_calculate_bearing_due_north():
    b = calculate_bearing(0.0, 0.0, 1.0, 0.0)
    assert abs(b - 0.0) < 0.01 or abs(b - 360.0) < 0.01


def test_calculate_bearing_due_east():
    b = calculate_bearing(0.0, 0.0, 0.0, 1.0)
    assert abs(b - 90.0) < 0.01


def test_calculate_bearing_due_south():
    b = calculate_bearing(1.0, 0.0, 0.0, 0.0)
    assert abs(b - 180.0) < 0.01


def test_calculate_bearing_due_west():
    b = calculate_bearing(0.0, 0.0, 0.0, -1.0)
    assert abs(b - 270.0) < 0.01


def test_bearing_to_cardinal_cardinals():
    assert bearing_to_cardinal(0) == "N"
    assert bearing_to_cardinal(45) == "NE"
    assert bearing_to_cardinal(90) == "E"
    assert bearing_to_cardinal(135) == "SE"
    assert bearing_to_cardinal(180) == "S"
    assert bearing_to_cardinal(225) == "SW"
    assert bearing_to_cardinal(270) == "W"
    assert bearing_to_cardinal(315) == "NW"
    # Rounds to nearest
    assert bearing_to_cardinal(22) == "N"
    assert bearing_to_cardinal(23) == "NE"


def test_haversine_zero_distance():
    assert haversine_distance_meters(32.9, -97.0, 32.9, -97.0) == 0.0


def test_haversine_approx_one_degree_lat():
    # 1 degree latitude ≈ 111 km
    d = haversine_distance_meters(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < d < 112_000


def test_haversine_symmetry():
    d1 = haversine_distance_meters(32.89, -97.04, 32.90, -97.05)
    d2 = haversine_distance_meters(32.90, -97.05, 32.89, -97.04)
    assert abs(d1 - d2) < 1e-6


def test_direction_instruction_first_step():
    # No previous direction → "Head ..."
    assert get_direction_instruction(1, 2, None, "N") == "Head N"


def test_direction_instruction_straight():
    assert get_direction_instruction(1, 2, "N", "N") == "Continue straight"


def test_direction_instruction_right_turn():
    # N → E is a right turn
    assert get_direction_instruction(1, 2, "N", "E") == "Turn right"


def test_direction_instruction_left_turn():
    # N → W is a left turn
    assert get_direction_instruction(1, 2, "N", "W") == "Turn left"


def test_direction_instruction_u_turn():
    # N → S is a turn-around
    assert get_direction_instruction(1, 2, "N", "S") == "Turn around"
