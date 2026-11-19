import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import database
from src.job_sources import remotive


SAMPLE_LISTING = {
    "id": 12345,
    "url": "https://remotive.com/remote-jobs/qa/software-tester-12345?ref=api",
    "title": "Software Tester",
    "company_name": "Example Studio",
    "candidate_required_location": "Poland",
    "job_type": "full_time",
    "salary": "",
    "publication_date": "2026-11-12T10:00:00",
    "description": "<p>Test web applications.</p>",
}


class TestRemotiveSource(unittest.TestCase):
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

    def test_normalize_listing_maps_source_fields(self):
        job = remotive.normalize_job(SAMPLE_LISTING)

        self.assertEqual(job["source"], "remotive")
        self.assertEqual(job["source_job_id"], "12345")
        self.assertEqual(
            job["normalized_url"],
            "https://remotive.com/remote-jobs/qa/software-tester-12345",
        )
        self.assertEqual(job["location"], "Poland")
        self.assertEqual(job["job_type"], "full_time")
        self.assertEqual(job["status"], "active")

    @patch("src.job_sources.remotive.urlopen")
    def test_fetch_enforces_limit_even_if_api_returns_more(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(
            {"jobs": [SAMPLE_LISTING, {**SAMPLE_LISTING, "id": 67890}]}
        ).encode("utf-8")
        urlopen.return_value = response

        jobs = remotive.fetch_jobs(limit=1)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], 12345)
        self.assertIn("limit=1", urlopen.call_args.args[0].full_url)

    @patch("src.job_sources.remotive.fetch_jobs", return_value=[SAMPLE_LISTING])
    def test_sync_saves_and_deduplicates_listing(self, fetch_jobs):
        self.assertEqual(remotive.sync_jobs(limit=1), 1)
        first_count = database.count_jobs()

        self.assertEqual(remotive.sync_jobs(limit=1), 1)
        self.assertEqual(database.count_jobs(), first_count)
        fetch_jobs.assert_called_with(search=None, limit=1)

        with database.db_connection() as connection:
            row = connection.execute(
                "SELECT source, title, location, job_type FROM jobs"
            ).fetchone()

        self.assertEqual(tuple(row), ("remotive", "Software Tester", "Poland", "full_time"))


if __name__ == "__main__":
    unittest.main()
