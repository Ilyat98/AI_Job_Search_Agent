import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from src.excel_exporter import export_jobs


class TestExcelExporter(unittest.TestCase):
    def test_exports_rejected_near_matches_on_separate_review_sheet(self):
        review = {
            "title": "Manual QA Engineer",
            "url": "https://example.com/manual-qa",
            "fit_score": 52,
            "ai_decision": "Not a match",
            "evaluation_source": "Ollama",
            "evaluation_confidence": "low",
            "missing_requirements": ["Postman"],
            "fit_warnings": ["Middle level: less than 12 months of experience"],
            "model_score": 42,
            "rule_score": 68,
            "model_comment": "Related experience; limited commercial QA experience.",
            "report_decision_label": "Manual review",
            "match_explanation": "Model score: 40/100; Postman is unconfirmed.",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "vacancies.xlsx"
            export_jobs([], review_jobs=[review], output_path=path)
            workbook = load_workbook(path, data_only=True)

        self.assertEqual(workbook.sheetnames, ["Vacancies", "Manual Review"])
        self.assertEqual(workbook["Vacancies"].max_row, 3)
        review_sheet = workbook["Manual Review"]
        self.assertEqual(review_sheet.cell(2, 1).value, "Manual QA Engineer")
        self.assertEqual(review_sheet.cell(2, 8).value, "Postman")
        self.assertEqual(review_sheet.cell(2, 10).value, "Manual review")
        self.assertEqual(review_sheet.cell(2, 13).value, 42)
        self.assertEqual(review_sheet.cell(2, 14).value, 68)
        self.assertIn("Middle", review_sheet.cell(2, 15).value)
        self.assertIn("commercial QA", review_sheet.cell(2, 16).value)
        self.assertIn("not recommendations", review_sheet.cell(4, 1).value)

    def test_exports_requested_columns_links_salary_and_color_bands(self):
        jobs = [
            {
                "title": f"QA role {score}",
                "url": f"https://example.com/{score}",
                "published_at": "2026-11-12T10:00:00+00:00",
                "salary": None if score == 45 else "PLN 10 000",
                "fit_score": score,
                "job_type": "full_time",
                "location": "Wrocław, Poland",
                "description": "Remote full-time B2B contract",
                "previously_seen": score == 45,
            }
            for score in (45, 60, 80, 90, 97)
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "vacancies.xlsx"
            export_jobs(jobs, output_path=path)
            sheet = load_workbook(path, data_only=True).active

        self.assertEqual(
            [cell.value for cell in sheet[1]],
            [
                "Job title", "Link", "Publication date", "Salary",
                "Fit score, %", "Employment / contract type", "Work mode / location",
                "Unconfirmed mandatory requirements",
                "Recommended CV", "Agent decision", "Assessment confidence", "Why it matches",
                "Ollama score, %", "Rule score, %", "Seniority / experience risk",
                "Ollama comment (verify)",
            ],
        )
        self.assertEqual(sheet.max_row, 8)
        rows_by_score = {sheet.cell(row, 5).value: row for row in range(2, 7)}
        expected_colors = {
            45: "FFF4CCCC",
            60: "FFFFE599",
            80: "FFD9EAD3",
            90: "FFCFE2F3",
            97: "FFD9D2E9",
        }
        for score, expected_color in expected_colors.items():
            self.assertEqual(
                sheet.cell(rows_by_score[score], 5).fill.fgColor.rgb,
                expected_color,
            )
        self.assertEqual(sheet.cell(rows_by_score[45], 4).value, "—")
        self.assertEqual(sheet.cell(rows_by_score[45], 6).value, "Full-time · B2B")
        self.assertEqual(sheet.cell(rows_by_score[45], 7).value, "Remote (Wrocław, Poland)")
        self.assertEqual(sheet.cell(rows_by_score[45], 8).value, "—")
        self.assertEqual(sheet.cell(rows_by_score[45], 9).value, "—")
        self.assertEqual(sheet.cell(rows_by_score[45], 10).value, "Not evaluated")
        self.assertEqual(sheet.cell(rows_by_score[45], 11).value, "—")
        self.assertEqual(sheet.cell(rows_by_score[45], 12).value, "—")
        self.assertEqual(
            sheet.cell(rows_by_score[45], 1).font.color.rgb,
            "FFED7D31",
        )
        self.assertNotEqual(
            sheet.cell(rows_by_score[60], 1).font.color.rgb,
            "FFED7D31",
        )

    def test_why_column_prefers_explanation_with_rule_evidence(self):
        job = {
            "title": "QA Engineer",
            "url": "https://example.com/qa",
            "fit_score": 65,
            "ai_summary": "Model score: 60/100; confidence: medium.",
            "match_explanation": (
                "Model score: 60/100; confidence: medium.; "
                "Unconfirmed mandatory requirements: TypeScript"
            ),
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "vacancies.xlsx"
            export_jobs([job], output_path=path)
            sheet = load_workbook(path, data_only=True).active

        self.assertIn("TypeScript", sheet.cell(2, 12).value)


if __name__ == "__main__":
    unittest.main()
