import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from src import database
from src.job_search import _evaluate_listings, filter_relevant_listings, run_pipeline


class TestJobSearchPipeline(unittest.TestCase):
    def test_replanning_queries_cannot_add_new_target_occupations(self):
        cutoff = datetime(2026, 11, 1, tzinfo=timezone.utc)
        jobs = [
            {"title": "QA Engineer", "status": "active"},
            {"title": "Python Developer", "status": "active"},
            {"title": "Linux System Administrator", "status": "active"},
        ]

        relevant, role_match_count = filter_relevant_listings(
            jobs,
            ["QA Engineer"],
            cutoff,
            "Europe/Warsaw",
        )

        self.assertEqual(role_match_count, 1)
        self.assertEqual([job["title"] for job in relevant], ["QA Engineer"])

    def test_invalid_response_uses_fallback_for_one_job_and_continues(self):
        profile = {
            "source_file": "QA.pdf",
            "ai_profile": {
                "skills": ["Python", "Selenium"],
                "experience": ["QA Engineer"],
                "languages": [],
            },
        }
        jobs = [
            {
                "source": "dou",
                "url": f"https://example.com/jobs/{index}",
                "normalized_url": f"https://example.com/jobs/{index}",
                "title": "QA Engineer",
                "description": "Python and Selenium testing",
                "status": "active",
            }
            for index in (1, 2)
        ]
        settings = {
            "ai": {
                "enabled": True,
                "model": "qwen2.5:3b",
                "base_url": "http://localhost:11434",
            },
            "agent": {},
            "job_matching": {},
        }

        with (
            patch("src.job_search.database.get_cached_job_evaluation", return_value=None),
            patch("src.job_search.database.save_cached_job_evaluation"),
            patch(
                "src.job_search.evaluate_job_with_ollama",
                side_effect=[ValueError("malformed model response"), [{"source_file": "QA.pdf"}]],
            ) as evaluate,
            patch(
                "src.job_search.combine_job_assessments",
                return_value={"fit_score": 80, "evaluation_source": "Ollama"},
            ),
        ):
            results, ollama_failed, ai_count, cache_count = _evaluate_listings(
                jobs, [profile], settings
            )

        self.assertEqual(evaluate.call_count, 2)
        self.assertFalse(ollama_failed)
        self.assertEqual(ai_count, 1)
        self.assertEqual(cache_count, 0)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["evaluation_source"].startswith("Rules (fallback)"))
        self.assertEqual(results[1]["evaluation_source"], "Ollama")

    def test_reuse_mode_scores_saves_and_exports_only_target_roles(self):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        settings = {
            "app": {"timezone": "Europe/Warsaw"},
            "search": {
                "initial_lookback_days": 7,
                "daily_lookback_hours": 24,
                "minimum_fit_score": 0,
            },
            "job_sources": {"enabled": ["dou"]},
            "job_categories": ["QA Engineer"],
        }
        profile = {
            "source_file": "QA.pdf",
            "ai_profile": {
                "skills": ["Python", "SQL", "Selenium"],
                "experience": ["QA Engineer"],
                "languages": [],
            },
        }
        listings = [
            {
                "source": "dou",
                "source_job_id": "qa-1",
                "url": "https://jobs.dou.ua/companies/example/vacancies/qa-1/",
                "normalized_url": "https://jobs.dou.ua/companies/example/vacancies/qa-1",
                "company": "Example",
                "title": "QA Engineer",
                "description": "B2B, Python, SQL, Selenium. Manual testing.",
                "location": "Warszawa, Poland",
                "job_type": "full_time",
                "salary": None,
                "published_at": now,
                "status": "active",
            },
            {
                "source": "dou",
                "source_job_id": "dev-1",
                "url": "https://jobs.dou.ua/companies/example/vacancies/dev-1/",
                "normalized_url": "https://jobs.dou.ua/companies/example/vacancies/dev-1",
                "company": "Example",
                "title": "Senior Data Engineer",
                "description": "Python, SQL",
                "location": "Wrocław, Poland",
                "job_type": "full_time",
                "salary": None,
                "published_at": now,
                "status": "active",
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "test.db"
            workbook_path = root / "vacancies.xlsx"
            with (
                patch.object(database, "DATA_DIR", root),
                patch.object(database, "DATABASE_PATH", db_path),
                patch("src.job_search.load_settings", return_value=settings),
                patch("src.job_search.load_current_profiles", return_value=[profile]),
                patch("src.job_search.fetch_enabled_sources", return_value=(listings, [], ["dou"])),
            ):
                result = run_pipeline(analyze_profiles=False, output_path=workbook_path)

                self.assertEqual(result, workbook_path)
                self.assertEqual(database.count_jobs(), 1)
                self.assertFalse(database.is_initial_search())

                run_pipeline(analyze_profiles=False, output_path=workbook_path)
                self.assertEqual(database.count_jobs(), 1)

            sheet = load_workbook(workbook_path, data_only=True).active
            self.assertEqual(sheet.max_row, 4)
            self.assertEqual(sheet.cell(2, 1).value, "QA Engineer")
            self.assertEqual(sheet.cell(2, 4).value, "—")
            self.assertEqual(sheet.cell(2, 6).value, "Full-time · B2B")
            self.assertEqual(sheet.cell(2, 7).value, "Format not specified (Warszawa, Poland)")
            self.assertEqual(sheet.cell(2, 1).font.color.rgb, "FFED7D31")


if __name__ == "__main__":
    unittest.main()
