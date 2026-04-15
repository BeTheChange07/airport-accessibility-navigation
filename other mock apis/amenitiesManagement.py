import os
import time
import random
import argparse
import threading
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

# NOTE: each thread should ideally use its own connection
def create_connection():
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    conn.autocommit = True
    return conn


def exit_handler(connections):
    for conn in connections:
        try:
            conn.close()
        except:
            pass


STATUS_OPTIONS = [
    "open",
    "closed",
    "maintenance",
    "busy",
    "out_of_service"
]


# -------- LOOP 1: RANDOM STATUS UPDATES --------
def update_random_amenities(conn, count):
    with conn.cursor() as cur:
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
            status = random.choice(STATUS_OPTIONS)

            cur.execute("""
                UPDATE amenities
                SET status = %s,
                    lastupdated = %s
                WHERE id = %s
            """, (status, now, amenity_id))

            print(f"[STATUS] Amenity {amenity_id} -> {status}")


def status_loop(interval, count):
    conn = create_connection()
    try:
        while True:
            update_random_amenities(conn, count)
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()


# -------- LOOP 2: USER REPORT HANDLING (STUB) --------
def process_user_reports(conn):
    """
    Placeholder for future logic.
    - table: userrReports
    - fields: ID, amenityID, reportType, description, status, createdAt, lastUpdated
    """
    with conn.cursor() as cur:
        pass

def report_loop(interval):
    conn = create_connection()
    try:
        while True:
            process_user_reports(conn)
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()


# -------- MAIN --------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Amenity status + report processor")
    parser.add_argument("--status-interval", type=float, default=5,
                        help="Seconds between random status updates")
    parser.add_argument("--status-count", type=int, default=1,
                        help="Amenities updated per status cycle")
    parser.add_argument("--report-interval", type=float, default=3,
                        help="Seconds between report processing cycles")

    args = parser.parse_args()

    # Start threads
    t1 = threading.Thread(target=status_loop, args=(args.status_interval, args.status_count), daemon=True)
#    t2 = threading.Thread(target=report_loop, args=(args.report_interval,), daemon=True)

    t1.start()
#    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")