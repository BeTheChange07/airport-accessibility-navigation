from typing import Any
import os, dotenv
import psycopg2 as pg

from coordinator import INFRASTRUCTURE_TABLE_NAME, AMENITY_TABLE_NAME

_conn = None

def connect():
    dotenv.load_dotenv()
    global _conn
    if _conn is not None:
        try:
            # Check if connection is still alive
            _conn.cursor().execute("SELECT 1;")
            return _conn
        except (pg.OperationalError, pg.InterfaceError):
            print("Connection lost. Reconnecting...")

    try:
        _conn = pg.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            cursor_factory=pg.RealDictCursor  # Returns dicts instead of tuples
        )
        print("Database connection established.")
        return _conn
    except pg.OperationalError as e:
        print(f"Error connecting to database: {e}")
        _conn = None
        return None

def _ensure_connection():
    global _conn
    if _conn is None:
        connect()
    else:
        try:
            with _conn.cursor() as cur:
                cur.execute("SELECT 1;")
        except (pg.OperationalError, pg.InterfaceError):
            print("Connection lost. Reconnecting...")
            connect()

def disconnect():
    global _conn
    if _conn:
        _conn.close()
        _conn = None
        print("Database connection closed.")
    else:
        print("No active database connection to close.")

def fetchEntireTable(tableName: str) -> list[dict[str, Any]]:
    query = f'SELECT * FROM "{tableName}";'  # quote to handle case-sensitive table names
    with _conn.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    return rows

def updateAmenity(data: list[dict[str, Any]]): #TODO
    _ensure_connection()

def updateInfrastructure(data: list[dict[str, Any]]): #TODO
    _ensure_connection()