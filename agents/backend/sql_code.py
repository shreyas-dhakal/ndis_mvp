import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))

with open("spine_schema.sql", "r") as f:
    sql = f.read().replace("{{EMBEDDING_DIM}}", str(EMBEDDING_DIM))

conn_string = os.getenv("DATABASE_URL")
if not conn_string:
    raise RuntimeError("DATABASE_URL not found — check your .env file")

with psycopg.connect(conn_string, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)

print("Schema applied successfully.")

# Quick verification — show columns on records table
with psycopg.connect(conn_string, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'records'
            ORDER BY ordinal_position
        """)
        print("\nrecords table columns:")
        for row in cur.fetchall():
            print(f"  {row[0]}: {row[1]}")
