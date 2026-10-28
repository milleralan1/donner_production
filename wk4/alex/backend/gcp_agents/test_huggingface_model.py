import os
import unittest
from unittest.mock import patch

from gcp_agents.huggingface_model import create_llm_model, get_llm_config


class LLMModelTests(unittest.TestCase):
    def test_uses_shared_huggingface_configuration(self):
        with (
            patch.dict(
                os.environ,
                {
                    "ALEX_LLM_PROVIDER": "huggingface",
                    "HF_TOKEN": "test-token",
                },
                clear=True,
            ),
            patch("gcp_agents.huggingface_model.AsyncOpenAI") as client_factory,
            patch(
                "gcp_agents.huggingface_model.OpenAIChatCompletionsModel"
            ) as model_factory,
        ):
            model = create_llm_model()

        self.assertIs(model, model_factory.return_value)
        client_factory.assert_called_once_with(
            api_key="test-token",
            base_url="https://router.huggingface.co/v1",
        )
        model_factory.assert_called_once_with(
            model="openai/gpt-oss-120b",
            openai_client=client_factory.return_value,
        )

    def test_uses_configured_provider_and_model(self):
        with patch.dict(
            os.environ,
            {
                "ALEX_LLM_PROVIDER": "nscale",
                "ALEX_LLM_MODEL": "meta-llama/Llama-3.1-8B-Instruct",
                "NSCALE_API_KEY": "test-nscale-key",
            },
            clear=True,
        ):
            config = get_llm_config("researcher")

        self.assertEqual(config.provider, "nscale")
        self.assertEqual(config.base_url, "https://inference.api.nscale.com/v1")
        self.assertEqual(config.api_key_env, "NSCALE_API_KEY")
        self.assertEqual(config.api_key, "test-nscale-key")
        self.assertEqual(config.model, "meta-llama/Llama-3.1-8B-Instruct")

    def test_rejects_missing_provider_key(self):
        with patch.dict(
            os.environ, {"ALEX_LLM_PROVIDER": "huggingface"}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, "HF_TOKEN"):
                get_llm_config()

    def test_rejects_missing_model_for_provider(self):
        with patch.dict(
            os.environ,
            {"ALEX_LLM_PROVIDER": "nscale", "NSCALE_API_KEY": "test-nscale-key"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "ALEX_LLM_MODEL"):
                get_llm_config("unconfigured-role")

    def test_rejects_unsupported_provider(self):
        with patch.dict(
            os.environ, {"ALEX_LLM_PROVIDER": "unknown"}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported ALEX_LLM_PROVIDER"):
                get_llm_config()


if __name__ == "__main__":
    unittest.main()
