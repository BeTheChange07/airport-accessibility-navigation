from typing import Any
import psycopg2 as pg

import env

_conn = None

def connect():
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
            host=env.DB_HOST,
            port=env.DB_PORT,
            dbname=env.DB_NAME,
            user=env.DB_USER,
            password=env.DB_PASS,
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
    _ensure_connection()
    query = f'SELECT * FROM "{tableName}";'  # quote to handle case-sensitive table names
    with _conn.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()

def updateAmenity(data: list[dict[str, Any]]): #TODO, sprint 2
    _ensure_connection()

def updateInfrastructure(data: list[dict[str, Any]]): #TODO, sprint 2
    _ensure_connection()