
import tempfile
import unittest
from pathlib import Path

from src import database


class TestDatabaseState(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_dir = database.DATA_DIR
        self.original_database_path = database.DATABASE_PATH

        test_dir = Path(self.temp_dir.name)
        database.DATA_DIR = test_dir
        database.DATABASE_PATH = test_dir / "test.db"

        database.init_db()

    def tearDown(self):
        database.DATA_DIR = self.original_data_dir
        database.DATABASE_PATH = self.original_database_path
        self.temp_dir.cleanup()

    def test_initial_search_is_pending(self):
        self.assertTrue(database.is_initial_search())

    def test_state_persists_after_reopening_connection(self):
        database.set_state("test_key", "saved_value")

        # The next read opens a new SQLite connection.
        value = database.get_state("test_key")

        self.assertEqual(value, "saved_value")

    def test_completed_initial_search_is_remembered(self):
        database.mark_initial_search_completed()

        self.assertFalse(database.is_initial_search())
        self.assertEqual(
            database.get_state("initial_search_completed"),
            "true",
        )

    def test_existing_job_urls_identifies_previous_results(self):
        listing = {
            "source": "test",
            "source_job_id": "1",
            "url": "https://example.com/jobs/1",
            "normalized_url": "https://example.com/jobs/1",
            "title": "QA Engineer",
        }
        database.save_job(listing)

        self.assertEqual(
            database.get_existing_job_urls([
                "https://example.com/jobs/1",
                "https://example.com/jobs/2",
            ]),
            {"https://example.com/jobs/1"},
        )

    def test_ai_profile_round_trip(self):
        cv_profile = {
            "source_file": "test_cv.pdf",
            "skills": ["Python", "SQL"],
            "languages": [
                {"name": "English", "level": "B2"},
            ],
            "job_titles": ["QA Engineer"],
            "sections": ["Experience", "Education"],
            "raw_text": "Test CV text",
        }

        ai_profile = {
            "skills": ["Python", "SQL", "Selenium"],
            "interests": ["automation"],
            "languages": [
                {"name": "English", "level": "B2"},
            ],
            "experience": [
                {
                    "employer": "Test Company",
                    "title": "QA Engineer",
                    "period": "2024-Present",
                    "duties": ["Manual testing"],
                }
            ],
            "education": [],
            "certificates": [],
            "projects": [],
            "unknowns": [],
        }

        database.save_cv_profile(cv_profile)
        database.save_ai_profile("test_cv.pdf", ai_profile)

        profiles = database.get_cv_profiles()

        self.assertEqual(len(profiles), 1)

        saved_profile = profiles[0]

        self.assertEqual(saved_profile["source_file"], "test_cv.pdf")
        self.assertEqual(saved_profile["skills"], ["Python", "SQL"])
        self.assertEqual(saved_profile["ai_profile"], ai_profile)
        self.assertEqual(saved_profile["ai_status"], "success")

    def test_changed_cv_text_invalidates_old_ai_profile(self):
        profile = {
            "source_file": "changing_cv.pdf",
            "raw_text": "Old CV text",
        }
        database.save_cv_profile(profile)
        database.save_ai_profile("changing_cv.pdf", {
            "skills": [],
            "interests": [],
            "languages": [],
            "experience": [],
            "education": [],
            "certificates": [],
            "projects": [],
            "unknowns": [],
        })

        database.save_cv_profile({
            "source_file": "changing_cv.pdf",
            "raw_text": "New CV text",
        })

        saved = database.get_cv_profiles()[0]
        self.assertIsNone(saved["ai_profile"])
        self.assertEqual(saved["ai_status"], "not_processed")

if __name__ == "__main__":
    unittest.main()
