import unittest

from pydantic import ValidationError

from guardrails import AnalyzeRequest


class AnalyzeRequestGuardrailTests(unittest.TestCase):
    def test_defaults_to_portfolio_analysis(self):
        request = AnalyzeRequest()
        self.assertEqual(request.analysis_type, "portfolio")
        self.assertEqual(request.options, {})

    def test_accepts_bounded_options(self):
        request = AnalyzeRequest(
            analysis_type="portfolio",
            options={"include_retirement": True},
        )
        self.assertEqual(request.options, {"include_retirement": True})

    def test_rejects_too_many_options(self):
        with self.assertRaises(ValidationError):
            AnalyzeRequest(options={f"option_{index}": index for index in range(33)})

    def test_rejects_oversized_options(self):
        with self.assertRaises(ValidationError):
            AnalyzeRequest(options={"description": "x" * 16_384})

    def test_rejects_overlong_analysis_type(self):
        with self.assertRaises(ValidationError):
            AnalyzeRequest(analysis_type="x" * 65)

    def test_rejects_empty_analysis_type(self):
        with self.assertRaises(ValidationError):
            AnalyzeRequest(analysis_type="")


if __name__ == "__main__":
    unittest.main()
