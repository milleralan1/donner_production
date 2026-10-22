"""Cloud SQL PostgreSQL client compatible with the existing database models."""

import json
import os
import re
import threading
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from .client import DataAPIClient

_NAMED_PARAMETER = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


class CloudSQLClient(DataAPIClient):
    """Use the Cloud SQL Python Connector while preserving the Data API interface."""

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

    @staticmethod
    def _parameter_map(parameters) -> Dict[str, Any]:
        if not parameters:
            return {}
        if isinstance(parameters, dict):
            return parameters

        values = {}
        for parameter in parameters:
            name = parameter["name"]
            value = parameter.get("value", {})
            if value.get("isNull"):
                values[name] = None
            elif value:
                values[name] = next(iter(value.values()))
            else:
                values[name] = None
        return values

    @classmethod
    def _prepare_statement(
        cls, sql: str, parameters
    ) -> Tuple[str, Tuple[Any, ...]]:
        values = cls._parameter_map(parameters)
        args = []

        def replace_parameter(match):
            name = match.group(1)
            if name not in values:
                raise ValueError(f"Missing SQL parameter: {name}")
            args.append(values[name])
            return "%s"

        statement = _NAMED_PARAMETER.sub(replace_parameter, sql)
        return statement, tuple(args)

    @staticmethod
    def _to_data_api_field(value: Any) -> Dict[str, Any]:
        if value is None:
            return {"isNull": True}
        if isinstance(value, bool):
            return {"booleanValue": value}
        if isinstance(value, int):
            return {"longValue": value}
        if isinstance(value, float):
            return {"doubleValue": value}
        if isinstance(value, bytes):
            return {"blobValue": value}
        if isinstance(value, (datetime, date)):
            return {"stringValue": value.isoformat()}
        if isinstance(value, Decimal):
            return {"stringValue": str(value)}
        if isinstance(value, (dict, list)):
            return {"stringValue": json.dumps(value)}
        return {"stringValue": str(value)}

    def execute(self, sql: str, parameters: List[Dict] = None) -> Dict:
        """Execute parameterized SQL and return the current Data API response shape."""
        statement, args = self._prepare_statement(sql, parameters)
        active_transaction = getattr(self._transaction, "active", None)
        connection = active_transaction[1] if active_transaction else self._connect()
        owns_connection = active_transaction is None
        cursor = None

        try:
            cursor = connection.cursor()
            cursor.execute(statement, args if args else None)
            columns = [description[0] for description in (cursor.description or [])]
            records = (
                [
                    [self._to_data_api_field(value) for value in row]
                    for row in cursor.fetchall()
                ]
                if columns
                else []
            )
            if owns_connection:
                connection.commit()
            return {
                "records": records,
                "columnMetadata": [{"name": name} for name in columns],
                "numberOfRecordsUpdated": max(cursor.rowcount or 0, 0),
            }
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
