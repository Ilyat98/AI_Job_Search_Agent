
import tempfile
import unittest
from pathlib import Path

from src import database


class TestCVProfiles(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_data_dir = database.DATA_DIR
        self.old_database_path = database.DATABASE_PATH

        database.DATA_DIR = Path(self.temp_dir.name)
        database.DATABASE_PATH = (
            Path(self.temp_dir.name) / "test.db"
        )

        database.init_db()

    def tearDown(self):
        database.DATA_DIR = self.old_data_dir
        database.DATABASE_PATH = self.old_database_path
        self.temp_dir.cleanup()

    def make_profile(self):
        return {
            "source_file": "QA.pdf",
            "skills": ["Python", "SQL"],
            "languages": [
                {"name": "English", "level": "B2"}
            ],
            "raw_text": "QA Engineer with Python and SQL.",
        }

    def test_saves_and_reads_profile(self):
        database.save_cv_profile(self.make_profile())

        profiles = database.get_cv_profiles()

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["source_file"], "QA.pdf")
        self.assertEqual(
            profiles[0]["skills"],
            ["Python", "SQL"],
        )
        self.assertEqual(
            profiles[0]["languages"][0]["level"],
            "B2",
        )

    def test_saving_same_file_updates_existing_profile(self):
        profile = self.make_profile()
        database.save_cv_profile(profile)

        profile["skills"] = ["Python", "Pytest"]
        database.save_cv_profile(profile)

        profiles = database.get_cv_profiles()

        self.assertEqual(database.count_cv_profiles(), 1)
        self.assertEqual(
            profiles[0]["skills"],
            ["Python", "Pytest"],
        )

    def test_profile_survives_new_database_connection(self):
        database.save_cv_profile(self.make_profile())

        profiles = database.get_cv_profiles()

        self.assertEqual(len(profiles), 1)
        self.assertIn("Python", profiles[0]["skills"])

    def test_saves_and_reads_job_titles_and_sections(self):
        profile = self.make_profile()
        profile["job_titles"] = ["QA Engineer", "Game Designer"]
        profile["sections"] = {
            "experience": "QA Engineer at Example Company",
            "education": "Bachelor degree in Electronics",
            "certificates": None,
        }

        database.save_cv_profile(profile)
        saved_profiles = database.get_cv_profiles()

        self.assertEqual(len(saved_profiles), 1)
        self.assertEqual(
            saved_profiles[0]["job_titles"],
            ["QA Engineer", "Game Designer"],
        )
        self.assertEqual(
            saved_profiles[0]["sections"]["education"],
            "Bachelor degree in Electronics",
        )
        self.assertIsNone(
            saved_profiles[0]["sections"]["certificates"]
        )

if __name__ == "__main__":
    unittest.main()
