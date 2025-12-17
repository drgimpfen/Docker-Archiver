import os
import psycopg2

def get_db_connection():
    """Return a new psycopg2 connection using `DATABASE_URL` and optional `DB_CONNECT_TIMEOUT`."""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set.")
    connect_timeout = int(os.environ.get('DB_CONNECT_TIMEOUT', '5'))
    return psycopg2.connect(database_url, connect_timeout=connect_timeout)
