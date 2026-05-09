"""Mock stall-lock sensor driver (UC5).

Simulates per-stall occupancy in `amenityunits`, then rolls each restroom's
unit states up to a bucket on `amenities.occupancy`. Restrooms only.

Instead of flipping stalls uniformly at random (which made every restroom
thrash every tick), each stall runs a tiny state machine:

    vacant  --p_fill-->  occupied
    occupied --p_drain-->  vacant

Most stalls don't change on any given tick, so occupancy trends smoothly
over minutes rather than teleporting between ticks.
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


def tick(p_fill, p_drain, count):
    """One simulation step.

    Picks `count` stalls (restrooms only) and probabilistically flips each
    based on its current state. Then re-aggregates every affected restroom's
    occupancy bucket from the stall states.
    """
    with conn.cursor() as cur:
        # Skip stalls touched in the last 30s. Admin "Full" / "Empty" / etc.
        # stamp every stall in the restroom with lastupdated=NOW(), so the
        # admin-set bucket sticks long enough for the demo (UC5 reroute
        # prompt, marker colour) before natural drift kicks back in.
        cur.execute("""
            SELECT u.unitid, u.amenityid, u.occupied
            FROM amenityunits u
            JOIN amenities a ON a.id = u.amenityid
            WHERE a.type = 'restroom'
              AND u.lastupdated < NOW() - INTERVAL '30 seconds'
            ORDER BY RANDOM()
            LIMIT %s
        """, (count,))
        units = cur.fetchall()
        if not units:
            return

        affected = set()
        for unit in units:
            currently_occupied = unit['occupied']
            prob = p_drain if currently_occupied else p_fill
            if random.random() < prob:
                next_state = not currently_occupied
                cur.execute("""
                    UPDATE amenityunits
                    SET occupied = %s, lastupdated = NOW()
                    WHERE unitid = %s AND amenityid = %s
                """, (next_state, unit['unitid'], unit['amenityid']))
                affected.add(unit['amenityid'])
                print(
                    f"[UC5] stall ({unit['amenityid']}, {unit['unitid']}) "
                    f"-> {'occupied' if next_state else 'vacant'}"
                )

        if not affected:
            return

        cur.execute("""
            UPDATE amenities
            SET occupancy = CASE
                    WHEN stats.total = 0 THEN amenities.occupancy
                    WHEN stats.occupied_count = stats.total THEN 'full'
                    WHEN stats.occupied_count::float / stats.total >= 0.66 THEN 'high'
                    WHEN stats.occupied_count::float / stats.total >= 0.33 THEN 'medium'
                    WHEN stats.occupied_count = 0 THEN 'empty'
                    ELSE 'low'
                END,
                lastupdated = NOW()
            FROM (
                SELECT amenityid,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE occupied = TRUE) AS occupied_count
                FROM amenityunits
                WHERE amenityid = ANY(%s)
                GROUP BY amenityid
            ) AS stats
            WHERE amenities.id = stats.amenityid
        """, (list(affected),))


def run_loop(interval, count, p_fill, p_drain):
    try:
        while True:
            tick(p_fill, p_drain, count)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopping occupancy sensor...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UC5 stall-lock sensor mock (restrooms only)")
    parser.add_argument("--interval", type=float, default=5,
                        help="Seconds between ticks (default: 5)")
    parser.add_argument("--count", type=int, default=20,
                        help="Stalls considered per tick (default: 20)")
    parser.add_argument("--p-fill", type=float, default=0.10,
                        help="Per-tick probability a vacant stall gets occupied (default: 0.10)")
    parser.add_argument("--p-drain", type=float, default=0.08,
                        help="Per-tick probability an occupied stall becomes vacant (default: 0.08)")
    args = parser.parse_args()

    run_loop(args.interval, args.count, args.p_fill, args.p_drain)
