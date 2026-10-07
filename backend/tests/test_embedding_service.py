import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from app.services import embedding_service


class EmbeddingServiceTests(TestCase):
    def call_with(self, provider, vectors, texts=None, **kwargs):
        client = Mock(return_value=vectors)
        module = SimpleNamespace(create_embeddings=client)
        with patch.object(embedding_service, "EMBEDDING_PROVIDER", provider):
            with patch.dict(sys.modules, {f"app.client_{provider}": module}):
                result = embedding_service.create_embeddings(
                    ["question"] if texts is None else texts, **kwargs,
                )
        return result, client

    def test_routes_both_providers(self):
        for provider in ("openai", "ollama"):
            with self.subTest(provider=provider):
                result, client = self.call_with(provider, [[0.1, 0.2]])
                self.assertEqual(result, [[0.1, 0.2]])
                client.assert_called_once_with(["question"])

    def test_empty_input_skips_request(self):
        result, client = self.call_with("ollama", [], texts=[])
        self.assertEqual(result, [])
        client.assert_not_called()

    def test_rejects_unknown_provider(self):
        with patch.object(embedding_service, "EMBEDDING_PROVIDER", "unknown"):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                embedding_service.create_embeddings(["question"])

    def test_rejects_index_dimension_mismatch(self):
        with self.assertRaisesRegex(ValueError, "Prepare a matching index"):
            self.call_with("ollama", [[0.1, 0.2]], expected_dimensions=1536)

    def test_rejects_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, "count"):
            self.call_with("ollama", [])

    def test_rejects_invalid_vectors(self):
        for vectors in ([[float("nan")]], [[float("inf")]], [[True]], [[]]):
            with self.subTest(vectors=vectors):
                with self.assertRaises(ValueError):
                    self.call_with("ollama", vectors)

    def test_rejects_inconsistent_dimensions(self):
        with self.assertRaisesRegex(ValueError, "dimensions"):
            self.call_with("ollama", [[0.1], [0.1, 0.2]], texts=["a", "b"])

    def test_qwen_query_instruction_is_not_applied_to_documents(self):
        storage = SimpleNamespace(embedding=SimpleNamespace(type=SimpleNamespace(dim=1024)))
        with patch.object(embedding_service, "EMBEDDING_PROVIDER", "ollama"):
            with patch.object(embedding_service, "get_embedding_index", return_value=(storage, "qwen3-embedding:0.6b")):
                with patch.object(embedding_service, "create_embeddings", return_value=[[0.1] * 1024]) as embed:
                    embedding_service.create_query_embedding("club run")
                    query = embed.call_args.args[0][0]
                    self.assertTrue(query.startswith("Instruct:"))
                    self.assertTrue(query.endswith("Query: club run"))
