import unittest

from src.search_planner import build_search_plan


class TestSearchPlanner(unittest.TestCase):
    def test_creates_only_tracks_supported_by_cv_experience(self):
        profiles = [
            {
                "ai_profile": {
                    "experience": [
                        "System Validation Engineer - Example (06/2023 - 12/2023)",
                        "Game Designer at Example Studio (02/2024 - Present)",
                        "Technical Support Engineer at Example Support",
                    ]
                }
            },
            {"ai_profile": {"experience": ["Electrical engineer at Example"]}},
        ]
        settings = {
            "job_categories": ["QA Engineer"],
            "job_sources": {
                "search_terms": ["QA"],
                "role_search_tracks": {
                    "qa": {
                        "cues": ["validation engineer", "qa"],
                        "search_terms": ["Manual QA", "Junior QA"],
                    },
                    "game_design": {
                        "cues": ["game designer"],
                        "search_terms": ["Gameplay Designer"],
                    },
                    "technical_support": {
                        "cues": ["technical support"],
                        "search_terms": ["IT Support Engineer"],
                    },
                    "electronics": {
                        "cues": ["electrical engineer"],
                        "search_terms": ["Electronics Technician"],
                    },
                    "python_development": {
                        "cues": ["python developer"],
                        "search_terms": ["Python Developer"],
                    },
                },
            },
            "user_preferences": {"preferred_roles": []},
        }

        plan = build_search_plan(profiles, settings)

        self.assertEqual(
            set(plan["tracks"]),
            {"qa", "game_design", "technical_support", "electronics"},
        )
        self.assertIn("Junior QA", plan["target_titles"])
        self.assertNotIn("Python Developer", plan["target_titles"])
        self.assertIn("Gameplay Designer", plan["expansion_terms"])


if __name__ == "__main__":
    unittest.main()
