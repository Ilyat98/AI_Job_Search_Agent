import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.job_sources import justjoin_sitemap


class TestJustJoinSitemap(unittest.TestCase):
    @patch("src.job_sources.justjoin_sitemap.urlopen")
    def test_reads_sitemap_and_parses_structured_job_details(self, urlopen):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sitemap_index = b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://justjoin.it/sitemaps/active-jobs/part0.xml</loc></sitemap>
        </sitemapindex>"""
        offers_sitemap = f"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://justjoin.it/job-offer/example-qa-engineer-warszawa</loc>
          <lastmod>{now}</lastmod></url>
          <url><loc>https://justjoin.it/job-offer/example-backend-developer</loc>
          <lastmod>{now}</lastmod></url>
        </urlset>""".encode()
        posting = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "QA Engineer",
            "datePosted": now,
            "validThrough": "2099-01-01T00:00:00Z",
            "description": "Testing with Python. B2B contract.",
            "employmentType": ["FULL_TIME", "CONTRACTOR"],
            "baseSalary": {
                "currency": "PLN",
                "value": {"minValue": 18000, "maxValue": 24000, "unitText": "MONTH"},
            },
            "hiringOrganization": {"name": "Example"},
            "jobLocationType": "TELECOMMUTE",
            "jobLocation": {
                "address": {"addressLocality": "Warszawa", "addressCountry": "PL"}
            },
        }
        page = (
            '<html><script type="application/ld+json">'
            + json.dumps(posting)
            + "</script></html>"
        ).encode()
        responses = []
        for payload in (sitemap_index, offers_sitemap, page):
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = payload
            responses.append(response)
        urlopen.side_effect = responses

        jobs = justjoin_sitemap.fetch_jobs(
            search_terms=["QA Engineer"], limit=5,
            since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Example")
        self.assertEqual(jobs[0]["location"], "Warszawa, Poland")
        self.assertEqual(jobs[0]["work_mode"], "remote")
        self.assertEqual(jobs[0]["salary"], "18 000–24 000 PLN / month")
        self.assertEqual(jobs[0]["status"], "active")
        self.assertEqual(jobs[0]["job_type"], "Full-time, Contractor")
        self.assertEqual(urlopen.call_count, 3)


if __name__ == "__main__":
    unittest.main()
