#!/usr/bin/env python3
"""Verify connectivity to the configured Cloud SQL PostgreSQL database."""

from src.models import Database


def main():
    database = Database()
    try:
        result = database.client.query_one(
            "SELECT current_database() AS database, current_timestamp AS server_time"
        )
        if not result:
            raise RuntimeError("Cloud SQL connected but returned no connection details")
        print(f"Connected to database {result['database']}")
        print(f"Server time: {result['server_time']}")
    finally:
        if hasattr(database.client, "close"):
            database.client.close()


if __name__ == "__main__":
    main()
