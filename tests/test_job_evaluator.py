import io
import json
import unittest
from unittest.mock import patch

from src.job_evaluator import (
    EVALUATION_SCHEMA,
    _ollama_chat,
    combine_job_assessments,
    evaluate_job_with_ollama,
    suggest_search_terms,
)


class TestOllamaChat(unittest.TestCase):
    def test_evaluation_schema_uses_compact_assessment_without_quote_lists(self):
        assessment_schema = EVALUATION_SCHEMA["properties"]["assessments"]["items"]
        self.assertNotIn("requirements", assessment_schema["properties"])
        self.assertEqual(assessment_schema["properties"]["summary"]["maxLength"], 160)

    def test_job_evaluation_selects_best_cv_and_sends_only_that_profile(self):
        profiles = [
            {
                "source_file": "Electronics.pdf",
                "ai_profile": {"skills": ["Arduino"], "experience": ["Electrical Engineer"]},
            },
            {
                "source_file": "QA.pdf",
                "ai_profile": {"skills": ["Python", "Playwright"], "experience": ["QA Engineer"]},
            },
            {
                "source_file": "Designer.pdf",
                "ai_profile": {"skills": ["Unity"], "experience": ["Game Designer"]},
            },
        ]
        settings = {"agent": {"evaluation_max_tokens": 512}}
        answer = {
            "assessments": [
                {
                    "cv_id": "cv_1",
                    "score": 72,
                    "decision": "possible_match",
                    "confidence": "medium",
                    "summary": "Relevant QA experience is present.",
                }
            ]
        }

        with patch("src.job_evaluator._ollama_chat", return_value=answer) as chat:
            result = evaluate_job_with_ollama(
                {"title": "QA Engineer", "description": "Python"},
                profiles,
                settings=settings,
            )

        self.assertEqual(chat.call_args.kwargs["max_tokens"], 512)
        submitted_candidates = chat.call_args.kwargs["user_payload"]["candidates"]
        self.assertEqual(len(submitted_candidates), 1)
        self.assertIn("Playwright", submitted_candidates[0]["skills"])
        self.assertEqual([item["source_file"] for item in result], ["QA.pdf"])

    def test_missing_assessment_is_retried_then_uses_rule_fallback(self):
        profiles = [
            {
                "source_file": "Electronics.pdf",
                "ai_profile": {"skills": ["Arduino"], "experience": ["Electrical Engineer"]},
            },
            {
                "source_file": "QA.pdf",
                "ai_profile": {"skills": ["Python", "Playwright"], "experience": ["QA Engineer"]},
            },
            {
                "source_file": "Designer.pdf",
                "ai_profile": {"skills": ["Unity"], "experience": ["Game Designer"]},
            },
        ]
        settings = {"agent": {"evaluation_max_tokens": 512}}

        with patch(
            "src.job_evaluator._ollama_chat",
            side_effect=[{"assessments": []}, {"assessments": []}],
        ) as chat:
            result = evaluate_job_with_ollama(
                {"title": "QA Engineer", "description": "Python"},
                profiles,
                settings=settings,
            )

        self.assertEqual(chat.call_count, 2)
        self.assertEqual([item["source_file"] for item in result], ["QA.pdf"])
        self.assertEqual(result[0]["evaluation_source"], "Rules")
        self.assertEqual(result[0]["confidence"], "low")

    def test_search_expansion_rejects_invented_roles_and_employer_names(self):
        profiles = [{
            "source_file": "QA.pdf",
            "ai_profile": {
                "skills": ["Python", "Unity"],
                "experience": [
                    "System Validation Engineer - Example Studio",
                    "Technical Support Engineer - YBC",
                ],
            },
        }]
        model_answer = {
            "terms": [
                '{"phrase":"Python Developer - Example Studio"}',
                "QA Automation Engineer",
                {"phrase": "Technical Support Specialist"},
                "System Validation Engineer - Example Studio",
            ]
        }

        with patch("src.job_evaluator._ollama_chat", return_value=model_answer):
            terms = suggest_search_terms(
                profiles,
                ["QA", "test automation"],
                settings={"agent": {"max_replan_terms": 5}},
            )

        self.assertEqual(terms, ["QA Automation Engineer", "Technical Support Specialist"])

    def test_combined_explanation_does_not_repeat_unverified_model_claims(self):
        profile = {
            "source_file": "QA.pdf",
            "ai_profile": {
                "skills": ["Python", "Playwright"],
                "experience": ["System Validation Engineer"],
                "languages": [],
            },
        }
        assessment = {
            "source_file": "QA.pdf",
            "score": 80,
            "decision": "strong_match",
            "confidence": "high",
            "summary": "Strong Python developer with shipped products.",
            "missing_required_skills": [],
            "requirements": [],
        }

        result = combine_job_assessments(
            {"title": "QA Engineer", "description": "Python testing"},
            [profile],
            [assessment],
            settings={"agent": {}, "job_matching": {}},
        )

        self.assertEqual(result["ai_summary"], "Model score: 80/100; confidence: high.")
        self.assertNotIn("shipped products", result["match_explanation"])

    def test_reports_invalid_model_json_with_location(self):
        response = io.BytesIO(b'{"message":{"content":"not json"}}')
        settings = {
            "ai": {
                "enabled": True,
                "provider": "ollama",
                "base_url": "http://localhost:11434",
                "model": "qwen2.5:3b",
                "request_timeout_seconds": 10,
            }
        }

        with patch("src.job_evaluator.urlopen", return_value=response):
            with self.assertRaisesRegex(
                ValueError,
                r"invalid assessment JSON: .*line 1, column",
            ):
                _ollama_chat(
                    settings=settings,
                    system_prompt="test",
                    user_payload={},
                    schema={"type": "object"},
                    max_tokens=100,
                )

    def test_reports_generation_truncation_separately_from_bad_json(self):
        response = io.BytesIO(json.dumps({
            "done_reason": "length",
            "eval_count": 1200,
            "message": {"content": '{"assessments":['},
        }).encode("utf-8"))
        settings = {
            "ai": {
                "enabled": True,
                "provider": "ollama",
                "base_url": "http://localhost:11434",
                "model": "qwen2.5:3b",
                "request_timeout_seconds": 10,
            }
        }

        with patch("src.job_evaluator.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "truncated the response at the generation limit"):
                _ollama_chat(
                    settings=settings,
                    system_prompt="test",
                    user_payload={},
                    schema={"type": "object"},
                    max_tokens=512,
                )


if __name__ == "__main__":
    unittest.main()
