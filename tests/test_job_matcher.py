import unittest

from src.job_matcher import (
    find_required_skills,
    is_target_role,
    missing_required_skills,
    missing_required_experience,
    profile_role_terms,
    seniority_mismatch_warning,
    score_job_for_profile,
)


class TestJobMatcher(unittest.TestCase):
    def test_scores_role_skills_and_related_experience(self):
        job = {
            "title": "QA Engineer",
            "description": "Testing with Python, SQL and Selenium. English required.",
        }
        profile = {
            "skills": ["Python", "SQL", "Selenium", "Playwright"],
            "experience": ["System Validation Engineer"],
            "languages": [{"name": "English", "level": "B2"}],
        }

        score, reasons = score_job_for_profile(job, profile)

        self.assertEqual(score, 75)
        self.assertTrue(any("Skills" in reason for reason in reasons))
        self.assertTrue(is_target_role(job))

    def test_unrelated_title_is_not_a_target_role(self):
        self.assertFalse(is_target_role({"title": "Senior Data Engineer"}))
        self.assertFalse(is_target_role({"title": "Ethical Hacker / Pentester"}))

    def test_role_terms_are_derived_from_profile_experience(self):
        profile = {"experience": [
            "Content Game Designer - Example Studio (01/2022 - Present)",
            "Technical Support Engineer - Example Services (02/2020 - 12/2021)",
            "Electrical engineer - Sample Employer",
            "Inżynier testów oprogramowania",
        ]}
        terms = profile_role_terms(profile)
        self.assertIn("Game Designer", terms)
        self.assertIn("Technical Support Engineer", terms)
        self.assertIn("Electrical engineer", terms)
        self.assertIn("Inżynier testów", terms)

    def test_score_rewards_matching_non_qa_cv_role_and_experience(self):
        score, reasons = score_job_for_profile(
            {"title": "Game Designer", "description": "Unity gameplay design"},
            {
                "skills": ["Unity"],
                "experience": ["Game Designer at Example Studio"],
                "languages": [],
            },
        )
        self.assertEqual(score, 53)
        self.assertTrue(any("role in the CV experience" in reason for reason in reasons))

    def test_requirement_parser_reads_ideal_candidate_heading(self):
        job = {
            "description": "Responsibilities. Our ideal candidate possesses "
            "the following skills: 3-5 years in QA, including JavaScript and "
            "TypeScript. Strong Playwright experience. Nice to have: Java. "
            "What we offer: training."
        }
        aliases = {
            "JavaScript": ["JavaScript"],
            "TypeScript": ["TypeScript", "Type Script"],
            "Playwright": ["Playwright"],
            "Java": ["Java"],
        }

        self.assertEqual(
            find_required_skills(job, aliases),
            ["JavaScript", "TypeScript", "Playwright"],
        )

    def test_requirement_parser_reads_ukrainian_heading(self):
        job = {
            "description": "Що для нас важливо: Linux і Python. "
            "Буде великим плюсом: Raspberry Pi. "
            "Що потрібно робити: Selenium testing."
        }
        aliases = {
            "Linux": ["Linux"],
            "Python": ["Python"],
            "Raspberry Pi": ["Raspberry Pi"],
            "Selenium": ["Selenium"],
        }

        self.assertEqual(find_required_skills(job, aliases), ["Linux", "Python"])

    def test_requirement_parser_reads_ukrainian_match_heading(self):
        job = {
            "description": "Наш метч, якщо ти: 2-3 роки досвіду, Jira і Postman. "
            "Буде плюсом: Playwright."
        }
        aliases = {
            "Jira": ["Jira"],
            "Postman": ["Postman"],
            "Playwright": ["Playwright"],
        }

        self.assertEqual(find_required_skills(job, aliases), ["Jira", "Postman"])

    def test_requirement_parser_splits_unpunctuated_curly_apostrophe_headings(self):
        job = {
            "description": "The team. What we’re looking for Conversational English. "
            "JavaScript. Nice to have Java. What you’ll be doing Build tests."
        }
        aliases = {
            "JavaScript": ["JavaScript"],
            "Java": ["Java"],
        }

        self.assertEqual(find_required_skills(job, aliases), ["JavaScript"])

    def test_missing_skill_check_respects_employer_stated_alternatives(self):
        job = {
            "description": "Basic JavaScript (or other scripting language). "
            "PostgreSQL (or another relational DB)."
        }
        profile = {"skills": ["Python", "SQL"], "experience": []}
        aliases = {
            "JavaScript": ["JavaScript"],
            "PostgreSQL": ["PostgreSQL", "Postgres"],
        }

        self.assertEqual(
            missing_required_skills(
                ["JavaScript", "PostgreSQL"], profile, aliases, job=job
            ),
            [],
        )

    def test_required_qa_years_are_compared_with_dated_relevant_experience(self):
        job = {
            "title": "QA Engineer",
            "description": "Required experience: 3+ years of QA/AQA experience. "
            "Python and Linux."
        }
        profile = {
            "experience": [
                "System Validation Engineer - Example Studio (06/2023 - 12/2023)",
                "Technical Support Engineer - Example Logistics (10/2020 - 03/2023)",
            ]
        }

        missing = missing_required_experience(job, profile)

        self.assertEqual(len(missing), 1)
        self.assertIn("requires 3+ years", missing[0])
        self.assertIn("about 7 mo.", missing[0])

    def test_required_game_design_years_can_be_confirmed_from_date_range(self):
        job = {
            "title": "Game Designer",
            "description": "What we expect: 2+ years of game design experience."
        }
        profile = {
            "experience": ["Game Designer at Example Studio (02/2024 - 08/2026)"]
        }

        self.assertEqual(missing_required_experience(job, profile), [])

    def test_senior_title_generates_soft_level_warning_from_relevant_dates(self):
        job = {"title": "Senior Test Automation Engineer", "description": "Python tests"}
        profile = {
            "experience": [
                "System Validation Engineer - Example Studio (06/2023 - 12/2023)",
                "Technical Support Engineer - Example Logistics (10/2020 - 03/2023)",
            ]
        }

        warning = seniority_mismatch_warning(job, profile)

        self.assertIn("Senior", warning)
        self.assertIn("7 mo.", warning)

    def test_middle_title_has_no_level_warning_with_two_years_related_experience(self):
        job = {"title": "Middle Game Designer", "description": "LiveOps"}
        profile = {
            "experience": ["Game Designer at Example Studio (02/2024 - 08/2026)"]
        }

        self.assertIsNone(seniority_mismatch_warning(job, profile))


if __name__ == "__main__":
    unittest.main()
