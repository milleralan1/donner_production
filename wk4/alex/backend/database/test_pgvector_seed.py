import json
import unittest

from seed_pgvector import (
    SEED_DOCUMENTS,
    SEED_SOURCE,
    SEED_TENANT_ID,
    build_seed_embedding,
    seed_pgvector,
)


class FakeClient:
    def __init__(self):
        self.queries = []

    def query(self, statement, parameters):
        self.queries.append((statement, parameters))
        if "MIN(vector_dims(embedding))" in statement:
            return [{"min_dimension": None, "max_dimension": None}]
        return [{"id": parameters["id"]}]

    def query_one(self, statement, parameters):
        rows = self.query(statement, parameters)
        return rows[0] if rows else None


class PgvectorSeedTests(unittest.TestCase):
    def test_seed_embedding_is_repeatable_and_normalized(self):
        embedding = build_seed_embedding("diversification", 8)

        self.assertEqual(embedding, build_seed_embedding("diversification", 8))
        self.assertEqual(len(embedding), 8)
        self.assertAlmostEqual(sum(value * value for value in embedding), 1.0)

    def test_seed_embedding_rejects_invalid_dimensions(self):
        for dimension in (0, 16_001, True):
            with self.subTest(dimension=dimension):
                with self.assertRaises(ValueError):
                    build_seed_embedding("invalid", dimension)

    def test_seed_upserts_isolated_documents_with_synthetic_vectors(self):
        client = FakeClient()

        count = seed_pgvector(client, 4)

        self.assertEqual(count, len(SEED_DOCUMENTS))
        insert_queries = [
            (statement, parameters)
            for statement, parameters in client.queries
            if "INSERT INTO research_documents" in statement
        ]
        self.assertEqual(len(insert_queries), len(SEED_DOCUMENTS))
        for (_, parameters), document in zip(insert_queries, SEED_DOCUMENTS):
            self.assertEqual(parameters["tenant_id"], SEED_TENANT_ID)
            self.assertEqual(parameters["content"], document["content"])
            self.assertEqual(
                json.loads(parameters["metadata"]),
                {
                    "seed_source": SEED_SOURCE,
                    "seed_id": document["seed_id"],
                    "synthetic_embedding": True,
                },
            )
            self.assertEqual(len(parameters["embedding"].strip("[]").split(",")), 4)

    def test_seed_refuses_a_mismatched_existing_embedding_dimension(self):
        class ExistingVectorsClient(FakeClient):
            def query(self, statement, parameters):
                if "MIN(vector_dims(embedding))" in statement:
                    return [{"min_dimension": 3, "max_dimension": 3}]
                return super().query(statement, parameters)

        with self.assertRaisesRegex(ValueError, "refusing to seed dimension 4"):
            seed_pgvector(ExistingVectorsClient(), 4)


if __name__ == "__main__":
    unittest.main()
