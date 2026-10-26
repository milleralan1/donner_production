"""Cloud SQL PostgreSQL client used by the database models."""

import json
import os
import re
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

_NAMED_PARAMETER = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


class CloudSQLClient:
    """Execute parameterized PostgreSQL queries through the Cloud SQL Connector."""

    # noinspection PyMissingConstructor
    def __init__(self, database: str = None, connector=None):
        try:
            from google.cloud.sql.connector import Connector, IPTypes
        except ImportError as error:
            raise ImportError(
                "Cloud SQL support requires the optional database dependency. "
                "Install it with `uv sync --extra gcp`."
            ) from error

        self.instance_connection_name = os.environ.get("CLOUD_SQL_CONNECTION_NAME")
        self.database = database or os.environ.get("DB_NAME", "alex")
        self.user = os.environ.get("DB_USER")
        self.password = os.environ.get("DB_PASSWORD")

        missing = [
            name
            for name, value in (
                ("CLOUD_SQL_CONNECTION_NAME", self.instance_connection_name),
                ("DB_USER", self.user),
                ("DB_PASSWORD", self.password),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing Cloud SQL configuration: " + ", ".join(missing)
            )

        ip_type = os.environ.get("CLOUD_SQL_IP_TYPE", "PUBLIC").upper()
        if ip_type not in {"PUBLIC", "PRIVATE"}:
            raise ValueError("CLOUD_SQL_IP_TYPE must be PUBLIC or PRIVATE")

        self._ip_type = IPTypes.PUBLIC if ip_type == "PUBLIC" else IPTypes.PRIVATE
        self._connector = connector or Connector()
        self._transaction = threading.local()

    def _connect(self):
        return self._connector.connect(
            self.instance_connection_name,
            "pg8000",
            user=self.user,
            password=self.password,
            db=self.database,
            ip_type=self._ip_type,
        )

    @classmethod
    def _prepare_statement(
        cls, sql: str, parameters
    ) -> Tuple[str, Tuple[Any, ...]]:
        values = parameters or {}
        if not isinstance(values, dict):
            raise TypeError("SQL parameters must be provided as a mapping")
        args = []

        def replace_parameter(match):
            name = match.group(1)
            if name not in values:
                raise ValueError(f"Missing SQL parameter: {name}")
            value = values[name]
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            args.append(value)
            return "%s"

        statement = _NAMED_PARAMETER.sub(replace_parameter, sql)
        return statement, tuple(args)

    def _run(self, sql: str, parameters=None):
        statement, args = self._prepare_statement(sql, parameters)
        active_transaction = getattr(self._transaction, "active", None)
        connection = active_transaction[1] if active_transaction else self._connect()
        owns_connection = active_transaction is None
        cursor = None

        try:
            cursor = connection.cursor()
            cursor.execute(statement, args)
            columns = [description[0] for description in (cursor.description or [])]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()] if columns else []
            if owns_connection:
                connection.commit()
            return rows, max(cursor.rowcount or 0, 0)
        except Exception:
            if owns_connection:
                connection.rollback()
            raise
        finally:
            try:
                if cursor:
                    cursor.close()
            finally:
                if owns_connection:
                    connection.close()

    def query(self, sql: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Execute a query and return rows as dictionaries."""
        rows, _ = self._run(sql, parameters)
        return rows

    def query_one(
        self, sql: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict]:
        """Return the first row of a query, if present."""
        rows = self.query(sql, parameters)
        return rows[0] if rows else None

    def execute(self, sql: str, parameters: Optional[Dict[str, Any]] = None) -> int:
        """Execute a statement and return its affected-row count."""
        _, rowcount = self._run(sql, parameters)
        return rowcount

    def insert(
        self, table: str, data: Dict[str, Any], returning: str = "id"
    ) -> Any:
        columns = list(data)
        names = ", ".join(columns)
        placeholders = ", ".join(f":{column}" for column in columns)
        row = self.query_one(
            f"INSERT INTO {table} ({names}) VALUES ({placeholders}) "
            f"RETURNING {returning}",
            data,
        )
        if row is None:
            raise RuntimeError(f"Insert into {table} returned no row")
        return row[returning]

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> int:
        if not data:
            return 0
        assignments = ", ".join(f"{column} = :{column}" for column in data)
        values = {**data, **(parameters or {})}
        return self.execute(f"UPDATE {table} SET {assignments} WHERE {where}", values)

    def delete(
        self,
        table: str,
        where: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> int:
        return self.execute(f"DELETE FROM {table} WHERE {where}", parameters)

    def begin_transaction(self) -> str:
        if getattr(self._transaction, "active", None):
            raise RuntimeError("A transaction is already active on this thread")
        transaction_id = str(uuid.uuid4())
        self._transaction.active = (transaction_id, self._connect())
        return transaction_id

    def commit_transaction(self, transaction_id: str):
        self._finish_transaction(transaction_id, commit=True)

    def rollback_transaction(self, transaction_id: str):
        self._finish_transaction(transaction_id, commit=False)

    def _finish_transaction(self, transaction_id: str, commit: bool):
        active = getattr(self._transaction, "active", None)
        if not active or active[0] != transaction_id:
            raise ValueError("Transaction is not active on this thread")
        _, connection = active
        try:
            connection.commit() if commit else connection.rollback()
        finally:
            connection.close()
            del self._transaction.active

    def close(self):
        """Close the connector and its background refresh resources."""
        self._connector.close()
