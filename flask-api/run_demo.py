"""One-shot demo launcher.

Starts Flask + the UC5 (occupancy) and UC6 (crowd) sensor mocks in
parallel, with their output prefixed so you can tell who said what.
On Ctrl+C, stops all three cleanly.

Usage:
    python run_demo.py

Does NOT run amenitiesManagement.py — the UC7 status is driven from the
admin portal (http://127.0.0.1:5000/admin), not a randomizer.
"""

import os
import signal
import subprocess
import sys
import threading
import time

from dotenv import dotenv_values


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
MOCK_DIR = os.path.join(REPO_ROOT, "other mock apis")
SQL_DIR = os.path.join(HERE, "SQL_FILES")

# Iteration-3 SQL files applied at startup, in order. Every file must be
# idempotent (IF NOT EXISTS / ON CONFLICT DO NOTHING) so re-launching the
# demo against a partially-migrated RDS is safe.
SCHEMA_FILES = [
    "iteration3_schema.sql",
    "iteration3_seed_demo.sql",
]

# Load flask-api/.env here and pass the resolved vars to every child. The
# mock scripts live in a different directory and their own `load_dotenv()`
# wouldn't find this file from their cwd.
_env_path = os.path.join(HERE, ".env")
_dotenv = dotenv_values(_env_path) if os.path.exists(_env_path) else {}
CHILD_ENV = {**os.environ, **{k: v for k, v in _dotenv.items() if v is not None}}

PROCS: "list[tuple[str, subprocess.Popen]]" = []


def _spawn(label: str, cwd: str, args: "list[str]", inherit_stdio: bool = False) -> None:
    """Start a child process. Two stdio modes:

    - inherit_stdio=False (default): pipe child stdout into a pump thread
      that prefixes each line. Good for sensor mocks that log infrequently.
    - inherit_stdio=True: child writes directly to the parent's terminal.
      Required for Flask — Werkzeug's request logger blocks if the pipe
      reader (PyCharm's console) gets behind, which truncates HTTP responses
      mid-stream and corrupts /api/amenities JSON on the Android client.
      Letting Flask write straight to stdout dodges that backpressure.
    """
    try:
        if inherit_stdio:
            proc = subprocess.Popen(
                args,
                cwd=cwd,
                env=CHILD_ENV,
                # No PIPE: child's stdout/stderr inherit parent's so writes
                # never block on a pipe buffer that no one is draining.
            )
        else:
            proc = subprocess.Popen(
                args,
                cwd=cwd,
                env=CHILD_ENV,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
            )
    except FileNotFoundError as e:
        print(f"[{label}] failed to start: {e}", flush=True)
        return
    PROCS.append((label, proc))

    if inherit_stdio:
        return

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(f"[{label}] {line.rstrip()}", flush=True)

    t = threading.Thread(target=pump, name=f"{label}-pump", daemon=True)
    t.start()


def _stop_all(sig_received: bool = False) -> None:
    """Terminate every child; escalate to kill if they don't exit promptly."""
    if not PROCS:
        return
    print("\n[demo] shutting down children...", flush=True)
    for label, proc in PROCS:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception as e:
                print(f"[demo] terminate({label}) failed: {e}", flush=True)
    deadline = time.time() + 5.0
    for label, proc in PROCS:
        remaining = max(0.0, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            print(f"[demo] {label} didn't exit in time; killing.", flush=True)
            try:
                proc.kill()
            except Exception:
                pass


def _install_signal_handlers() -> None:
    def handler(signum, frame):
        _stop_all(sig_received=True)
        # Re-raise default so the interpreter exits with the right code.
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handler)
        except (ValueError, AttributeError):
            # Some signals aren't available on Windows; ignore.
            pass


def _apply_schema_migrations() -> None:
    """Idempotently run the iteration-3 SQL files against RDS before launch.

    Safe to re-run: each file is gated on IF NOT EXISTS / ON CONFLICT DO
    NOTHING. If DB env vars are missing or the connection fails we log
    and continue -- Flask itself will surface the underlying problem on
    the first request rather than the launcher swallowing it silently.
    """
    db_kwargs = {
        "host":     CHILD_ENV.get("DB_HOST"),
        "port":     CHILD_ENV.get("DB_PORT", "5432"),
        "dbname":   CHILD_ENV.get("DB_NAME"),
        "user":     CHILD_ENV.get("DB_USER"),
        "password": CHILD_ENV.get("DB_PASSWORD"),
    }
    if not db_kwargs["host"] or not db_kwargs["dbname"]:
        print("[demo] DB env not set; skipping schema migration.", flush=True)
        return

    try:
        import psycopg2  # type: ignore
    except ImportError:
        print("[demo] psycopg2 not installed; skipping schema migration.",
              flush=True)
        return

    try:
        conn = psycopg2.connect(**db_kwargs)
    except Exception as e:
        print(f"[demo] could not connect to RDS for migration: {e}",
              flush=True)
        return

    try:
        with conn:
            with conn.cursor() as cur:
                for fname in SCHEMA_FILES:
                    fpath = os.path.join(SQL_DIR, fname)
                    if not os.path.exists(fpath):
                        print(f"[demo] {fname} missing; skipping.", flush=True)
                        continue
                    with open(fpath, "r", encoding="utf-8") as f:
                        sql = f.read()
                    cur.execute(sql)
                    print(f"[demo] applied {fname}.", flush=True)
    except Exception as e:
        print(f"[demo] schema migration failed: {e}", flush=True)
    finally:
        conn.close()


def main() -> int:
    _install_signal_handlers()
    _apply_schema_migrations()

    python = sys.executable

    _spawn(
        "flask",
        cwd=HERE,
        args=[python, os.path.join(HERE, "app.py")],
        inherit_stdio=True,
    )
    _spawn(
        "uc5-occupancy",
        cwd=MOCK_DIR,
        args=[python, os.path.join(MOCK_DIR, "occupancySensors.py"), "--interval", "5"],
    )
    _spawn(
        "uc6-crowd",
        cwd=MOCK_DIR,
        args=[python, os.path.join(MOCK_DIR, "crowdDetection.py"), "--interval", "5"],
    )

    try:
        while True:
            # If Flask itself dies, take the whole demo down.
            for label, proc in list(PROCS):
                code = proc.poll()
                if code is not None:
                    print(f"[demo] {label} exited (code={code}); stopping demo.",
                          flush=True)
                    _stop_all()
                    return code if code is not None else 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        _stop_all(sig_received=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
