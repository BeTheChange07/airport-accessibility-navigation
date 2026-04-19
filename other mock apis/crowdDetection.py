"""Mock queue-camera driver (UC6).

Simulates the Airport Crowd Detection System by updating
`amenities.crowdlevel` on each tick. Restrooms only.

Previous version wrote `randint(0, 100)` every tick, which made the wait
indicator teleport between ticks. This version does a bounded random walk:

    new = clamp(current + step, 0, 100)

so the needle drifts instead of jumping.
"""

import os
import time
import random
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import atexit

load_dotenv()

DB_CONFIG = {
    'host': os.environ.get('DB_HOST'),
    'port': os.environ.get('DB_PORT', '5432'),
    'dbname': os.environ.get('DB_NAME'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
}

conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
conn.autocommit = True


def exit_handler():
    try:
        conn.close()
    except Exception:
        pass


atexit.register(exit_handler)


def tick(count, step_max):
    """Walk `count` restrooms' crowdlevel by +/- up to step_max."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, COALESCE(crowdlevel, 0) AS crowdlevel
            FROM amenities
            WHERE type = 'restroom'
            ORDER BY RANDOM()
            LIMIT %s
        """, (count,))
        rows = cur.fetchall()
        if not rows:
            return

        for row in rows:
            current = int(row['crowdlevel'] or 0)
            step = random.randint(-step_max, step_max)
            new_level = max(0, min(100, current + step))
            cur.execute("""
                UPDATE amenities
                SET crowdlevel = %s, lastupdated = NOW()
                WHERE id = %s
            """, (new_level, row['id']))
            print(f"[UC6] amenity {row['id']} crowdlevel {current} -> {new_level}")


def run_loop(interval, count, step_max):
    try:
        while True:
            tick(count, step_max)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopping crowd detection...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UC6 crowd detection mock (restrooms only)")
    parser.add_argument("--interval", type=float, default=5,
                        help="Seconds between ticks (default: 5)")
    parser.add_argument("--count", type=int, default=5,
                        help="Restrooms updated per tick (default: 5)")
    parser.add_argument("--step", type=int, default=8,
                        help="Max +/- change per tick (default: 8)")
    args = parser.parse_args()

    run_loop(args.interval, args.count, args.step)
