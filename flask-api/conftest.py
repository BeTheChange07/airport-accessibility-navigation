"""Shared pytest fixtures for flask-api tests. Stubs out Postgres and NearestNodeFinder."""

import os
import sys
import types

# Dummy DB env vars so DB_CONFIG is populated.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")

# Stub NearestNodeFinder so we don't pull in numpy/scipy.
_fake_nnf_module = types.ModuleType("NearestNodeFinder")


class _FakeNearestNodeFinder:
    def __init__(self, coordinates):
        self.coordinates = coordinates

    def get_nearest_active_node(self, query_point, initial_k=10):
        # Always return index 0; tests seed the node list accordingly.
        return 0

    def deactivate_nodes(self, indices): pass
    def activate_nodes(self, indices): pass
    def set_active_mask(self, mask): pass


_fake_nnf_module.NearestNodeFinder = _FakeNearestNodeFinder  # type: ignore[attr-defined]
sys.modules.setdefault("NearestNodeFinder", _fake_nnf_module)

import psycopg2  # noqa: E402


class _ProbeCursor:
    """No-op stand-in for the liveness-probe cursor in app.py.

    `_ensure_db_alive` opens a ``with conn.cursor() as probe`` block,
    runs SELECT 1, and fetches one row before the route handler runs.
    Returning the shared singleton from ``__enter__`` would consume the
    fetchone queue the test queued for the handler, so we hand back this
    isolated stub instead.
    """
    def execute(self, sql, params=None): pass
    def fetchone(self): return None
    def fetchall(self): return []
    def close(self): pass


class FakeCursor:
    """Cursor with per-test queued fetchall/fetchone results."""

    def __init__(self):
        self._fetchall_queue = []
        self._fetchone_queue = []
        self.executed = []
        self.last_sql = None
        self.last_params = None

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        self.executed.append((sql, params))

    def fetchall(self):
        if self._fetchall_queue:
            return self._fetchall_queue.pop(0)
        return []

    def fetchone(self):
        if self._fetchone_queue:
            return self._fetchone_queue.pop(0)
        return None

    def close(self):
        pass

    # Used only by the liveness probe; routes never wrap the singleton
    # in `with`. Hand back a fresh stub so the probe's fetchone() doesn't
    # eat a queued response meant for the handler.
    def __enter__(self):
        return _ProbeCursor()

    def __exit__(self, exc_type, exc, tb):
        return False

    def queue_fetchall(self, rows):
        self._fetchall_queue.append(rows)

    def queue_fetchone(self, row):
        self._fetchone_queue.append(row)

    def reset(self):
        self._fetchall_queue.clear()
        self._fetchone_queue.clear()
        self.executed.clear()
        self.last_sql = None
        self.last_params = None


_fake_cursor_singleton = FakeCursor()


class _FakeConn:
    # psycopg2 exposes `closed` as an int (0 = open). The before_request
    # liveness probe reads this attribute, so the stub must too.
    closed = 0

    def cursor(self, *a, **k):
        return _fake_cursor_singleton

    def close(self): pass
    def rollback(self): pass
    def commit(self): pass


psycopg2.connect = lambda *a, **k: _FakeConn()  # type: ignore[assignment]

sys.path.insert(0, os.path.dirname(__file__))
import app as flask_app  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def client():
    """Flask test client."""
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


@pytest.fixture
def cur():
    """Shared FakeCursor for queueing scripted responses."""
    return flask_app.cur


@pytest.fixture(autouse=True)
def _reset_state_between_tests():
    """Reset the cursor and /api/nearest's KDTree cache between tests."""
    flask_app.cur.reset()
    if hasattr(flask_app.nearest_node, "finders"):
        flask_app.nearest_node.finders = {}
        flask_app.nearest_node.node_ids_by_key = {}
    # UC3 rate limit is process-local; clear so a previous test's submit
    # doesn't 429 the next one when both use the same client IP.
    if hasattr(flask_app, "_report_submit_last_seen"):
        flask_app._report_submit_last_seen.clear()
    yield
    flask_app.cur.reset()
