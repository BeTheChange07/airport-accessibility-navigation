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


def update_random_amenities(count):
    with conn.cursor() as cur:
        # Fetch random amenities
        cur.execute("""
            SELECT id
            FROM amenities
            ORDER BY RANDOM()
            LIMIT %s
        """, (count,))
        amenities = cur.fetchall()

        if not amenities:
            return

        now = datetime.now(timezone.utc)

        for amenity in amenities:
            amenity_id = amenity['id']

            # Generate random crowd level (adjust range as needed)
            crowd_level = random.randint(0, 100)

            cur.execute("""
                UPDATE amenities
                SET crowdlevel = %s,
                    lastupdated = %s
                WHERE id = %s
            """, (crowd_level, now, amenity_id))

            print(f"Updated amenity {amenity_id} -> crowdlevel={crowd_level}")


def run_loop(interval, count):
    try:
        while True:
            update_random_amenities(count)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Stopping updater...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Random amenity crowd level updater")
    parser.add_argument("--interval", type=float, default=5,
                        help="Seconds between update cycles (default: 5)")
    parser.add_argument("--count", type=int, default=1,
                        help="Number of amenities to update per cycle (default: 1)")

    args = parser.parse_args()

    run_loop(interval=args.interval, count=args.count)