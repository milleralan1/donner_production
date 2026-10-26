import os
import unittest
from unittest.mock import patch

from gcp_agents.groq_model import create_groq_model


class GroqModelTests(unittest.TestCase):
    def test_uses_configured_groq_model(self):
        with (
            patch.dict(
                os.environ,
                {
                    "GROQ_API_KEY": "test-key",
                    "GROQ_MODEL": "groq/llama-3.3-70b-versatile",
                },
                clear=True,
            ),
            patch("gcp_agents.groq_model.AsyncOpenAI") as client_factory,
            patch(
                "gcp_agents.groq_model.OpenAIChatCompletionsModel"
            ) as model_factory,
        ):
            model = create_groq_model()
            self.assertIs(model, model_factory.return_value)
            client_factory.assert_called_once_with(
                api_key="test-key",
                base_url="https://api.groq.com/openai/v1",
            )
            model_factory.assert_called_once_with(
                model="llama-3.3-70b-versatile",
                openai_client=client_factory.return_value,
            )

    def test_rejects_missing_api_key(self):
        with patch.dict(
            os.environ, {"GROQ_MODEL": "groq/llama-3.3-70b-versatile"}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, "GROQ_API_KEY"):
                create_groq_model()

    def test_rejects_missing_model(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True):
            with self.assertRaisesRegex(ValueError, "GROQ_MODEL"):
                create_groq_model()

    def test_rejects_non_groq_model(self):
        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "vertex_ai/model"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "groq/"):
                create_groq_model()


if __name__ == "__main__":
    unittest.main()
