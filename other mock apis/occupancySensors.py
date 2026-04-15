import os
import time
import random
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from datetime import datetime, timezone
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
    conn.close()

atexit.register(exit_handler)


def update_random_units(count):
    with conn.cursor() as cur:
        # Fetch random units
        cur.execute("""
            SELECT unitid, amenityid
            FROM amenityunits
            ORDER BY RANDOM()
            LIMIT %s
        """, (count,))
        units = cur.fetchall()

        if not units:
            return

        now = datetime.now(timezone.utc)

        for unit in units:
            unit_id = unit['unitid']
            amenity_id = unit['amenityid']
            occupied = random.choice([True, False])

            # Update unit
            cur.execute("""
                UPDATE amenityunits
                SET occupied = %s,
                    lastupdated = %s
                WHERE unitid = %s
            """, (occupied, now, unit_id))

            # Update parent amenity
            cur.execute("""
                UPDATE amenities
                SET lastupdated = %s
                WHERE id = %s
            """, (now, amenity_id))

            print(f"Updated unit {unit_id} -> occupied={occupied}")


def run_loop(interval, count):
    try:
        while True:
            update_random_units(count)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopping updater...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Random amenity unit occupancy updater")
    parser.add_argument("--interval", type=float, default=5,
                        help="Seconds between update cycles (default: 5)")
    parser.add_argument("--count", type=int, default=1,
                        help="Number of units to update per cycle (default: 1)")

    args = parser.parse_args()

    run_loop(interval=args.interval, count=args.count)