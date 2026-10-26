import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from src.cloud_sql_client import CloudSQLClient
from src.models import Database


class FakeCursor:
    description = [("id", None), ("payload", None), ("balance", None)]
    rowcount = 1

    def __init__(self):
        self.executed = None
        self.closed = False

    def execute(self, statement, parameters=None):
        self.executed = (statement, parameters)

    def fetchall(self):
        return [("abc", {"equity": 70}, Decimal("12.50"))]

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class FakeConnector:
    def __init__(self):
        self.connection = FakeConnection()

    def connect(self, *args, **kwargs):
        return self.connection

    def close(self):
        pass


class CloudSQLClientTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "CLOUD_SQL_CONNECTION_NAME": "project:region:instance",
                "DB_USER": "alex",
                "DB_PASSWORD": "test-password",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_prepare_statement_reuses_named_parameters_and_keeps_casts(self):
        statement, parameters = CloudSQLClient._prepare_statement(
            "SELECT :id::uuid WHERE parent_id = :id::uuid AND name = :name",
            {"id": "123", "name": "Alex"},
        )

        self.assertEqual(
            statement,
            "SELECT %s::uuid WHERE parent_id = %s::uuid AND name = %s",
        )
        self.assertEqual(parameters, ("123", "123", "Alex"))

    def test_prepare_statement_serializes_json_parameters(self):
        statement, parameters = CloudSQLClient._prepare_statement(
            "INSERT INTO jobs (request_payload) VALUES (:payload::jsonb)",
            {"payload": {"symbols": ["VTI", "BND"]}},
        )

        self.assertEqual(
            statement, "INSERT INTO jobs (request_payload) VALUES (%s::jsonb)"
        )
        self.assertEqual(parameters, ('{"symbols": ["VTI", "BND"]}',))

    def test_query_returns_postgres_rows(self):
        connector = FakeConnector()
        client = CloudSQLClient(connector=connector)

        result = client.query(
            "SELECT :id::uuid",
            {"id": "abc"},
        )

        self.assertEqual(connector.connection.cursor_instance.executed,
                         ("SELECT %s::uuid", ("abc",)))
        self.assertEqual(result, [{
            "id": "abc",
            "payload": {"equity": 70},
            "balance": Decimal("12.50"),
        }])
        self.assertEqual(connector.connection.commits, 1)
        self.assertTrue(connector.connection.closed)

    def test_query_without_parameters_passes_empty_tuple(self):
        connector = FakeConnector()
        client = CloudSQLClient(connector=connector)

        client.query("SELECT 1")

        self.assertEqual(
            connector.connection.cursor_instance.executed,
            ("SELECT 1", ()),
        )

    def test_database_uses_cloud_sql_client(self):
        connector = FakeConnector()
        with patch("google.cloud.sql.connector.Connector", return_value=connector):
            database = Database()

        self.assertIsInstance(database.client, CloudSQLClient)
        database.client.close()

    def test_transaction_reuses_connection_until_commit(self):
        connector = FakeConnector()
        client = CloudSQLClient(connector=connector)

        transaction_id = client.begin_transaction()
        client.execute("SELECT 1")
        self.assertEqual(connector.connection.commits, 0)
        self.assertFalse(connector.connection.closed)

        client.commit_transaction(transaction_id)
        self.assertEqual(connector.connection.commits, 1)
        self.assertTrue(connector.connection.closed)


if __name__ == "__main__":
    unittest.main()
