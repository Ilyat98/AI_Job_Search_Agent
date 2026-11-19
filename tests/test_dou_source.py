import unittest
from unittest.mock import MagicMock, patch

from src.job_sources import dou_rss


SAMPLE_FEED = b"""<?xml version='1.0' encoding='utf-8'?>
<rss version='2.0'><channel><title>QA</title><item>
<title>Tester manualny w Example Studio, Wroc\xc5\x82aw, remote</title>
<link>https://jobs.dou.ua/companies/example/vacancies/123/?utm_source=rss</link>
<description>&amp;lt;p&amp;gt;Manual testing. Salary $2000-2500.&amp;lt;/p&amp;gt;</description>
<pubDate>Fri, 13 Nov 2026 19:00:00 +0200</pubDate>
</item></channel></rss>"""


class TestDouRssSource(unittest.TestCase):
    @patch("src.job_sources.dou_rss.urlopen")
    def test_feed_normalizes_listing(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = SAMPLE_FEED
        urlopen.return_value = response

        jobs = dou_rss.fetch_jobs(search="QA", limit=5)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["source"], "dou")
        self.assertEqual(job["source_job_id"], "123")
        self.assertEqual(job["title"], "Tester manualny")
        self.assertEqual(job["company"], "Example Studio")
        self.assertEqual(job["location"], "Wrocław, remote")
        self.assertEqual(job["salary"], "$2000-2500")
        self.assertEqual(job["status"], "active")
        self.assertIn("search=QA", urlopen.call_args.args[0].full_url)

    @patch("src.job_sources.dou_rss.urlopen")
    def test_salary_in_rss_title_is_not_left_in_location(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = SAMPLE_FEED.replace(
            b"Tester manualny w Example Studio, Wroc\xc5\x82aw, remote",
            b"Manual QA Engineer at Example Studio, $1,500-2,000, Kyiv, remote",
        )
        urlopen.return_value = response

        job = dou_rss.fetch_jobs(search="QA", limit=5)[0]

        self.assertEqual(job["salary"], "$1,500-2,000")
        self.assertEqual(job["location"], "Kyiv, remote")


if __name__ == "__main__":
    unittest.main()
