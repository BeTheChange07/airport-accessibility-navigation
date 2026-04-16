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

        affected_amenities = set()

        for unit in units:
            unit_id = unit['unitid']
            amenity_id = unit['amenityid']
            occupied = random.choice([True, False])

            # Update unit using composite key + DB timestamp
            cur.execute("""
                UPDATE amenityunits
                SET occupied = %s,
                    lastupdated = NOW()
                WHERE unitid = %s
                  AND amenityid = %s
            """, (occupied, unit_id, amenity_id))

            affected_amenities.add(amenity_id)

            print(f"Updated unit ({amenity_id}, {unit_id}) -> occupied={occupied}")

        if not affected_amenities:
            return

        amenity_ids = list(affected_amenities)

        # Bulk update all affected amenities
        cur.execute("""
            UPDATE amenities
            SET 
                occupancy = CASE
                    WHEN stats.total = 0 THEN amenities.occupancy
                    WHEN stats.occupied_count = stats.total THEN 'full'
                    WHEN stats.occupied_count::float / stats.total >= 0.66 THEN 'high'
                    WHEN stats.occupied_count::float / stats.total >= 0.33 THEN 'medium'
                    WHEN stats.occupied_count = 0 THEN 'empty'
                    ELSE 'low'
                END,
                lastupdated = NOW()
            FROM (
                SELECT 
                    amenityid,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE occupied = true) AS occupied_count
                FROM amenityunits
                WHERE amenityid = ANY(%s)
                GROUP BY amenityid
            ) AS stats
            WHERE amenities.id = stats.amenityid
        """, (amenity_ids,))

        print(f"Updated {len(amenity_ids)} amenities (occupancy + timestamp)")


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