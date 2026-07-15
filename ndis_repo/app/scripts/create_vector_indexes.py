import sys

from app.db.pgvector_adapter import close_pool, connect
from app.db.schema import ensure_schema


def main() -> None:
    try:
        with connect() as conn:
            ensure_schema(conn)
            conn.commit()
    finally:
        close_pool()
    print("Schema and vector indexes ensured")


if __name__ == "__main__":
    sys.exit(main())
