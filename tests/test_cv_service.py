
import unittest
from pathlib import Path
from unittest.mock import call, patch

from src.cv_service import process_all_cvs


class TestCVService(unittest.TestCase):

    @patch("src.cv_service.save_ai_profile")
    @patch("src.cv_service.extract_ai_profile")
    @patch("src.cv_service.save_cv_profile")
    @patch("src.cv_service.build_profile")
    @patch("src.cv_service.discover_cv_files")
    def test_processes_all_cvs(
        self,
        mock_discover,
        mock_build,
        mock_save_cv,
        mock_extract_ai,
        mock_save_ai,
    ):
        mock_discover.return_value = [
            Path("QA.pdf"),
            Path("Designer.pdf"),
        ]

        mock_build.side_effect = [
            {
                "source_file": "QA.pdf",
                "raw_text": "QA Engineer with Python experience.",
            },
            {
                "source_file": "Designer.pdf",
                "raw_text": "Game Designer with Unity experience.",
            },
        ]

        mock_extract_ai.side_effect = [
            {
                "skills": ["Python"],
                "languages": [],
                "experience": [],
                "education": [],
                "certificates": [],
                "projects": [],
                "unknowns": [],
            },
            {
                "skills": ["Unity"],
                "languages": [],
                "experience": [],
                "education": [],
                "certificates": [],
                "projects": [],
                "unknowns": [],
            },
        ]

        saved_count = process_all_cvs()

        self.assertEqual(saved_count, 2)
        self.assertEqual(mock_build.call_count, 2)
        self.assertEqual(mock_save_cv.call_count, 2)
        self.assertEqual(mock_extract_ai.call_count, 2)
        self.assertEqual(mock_save_ai.call_count, 2)

        mock_extract_ai.assert_any_call(
            "QA Engineer with Python experience."
        )
        mock_extract_ai.assert_any_call(
            "Game Designer with Unity experience."
        )

        expected_qa_profile = {
            "skills": ["Python"],
            "languages": [],
            "experience": [],
            "education": [],
            "certificates": [],
            "projects": [],
            "unknowns": [],
        }

        expected_designer_profile = {
            "skills": ["Unity"],
            "languages": [],
            "experience": [],
            "education": [],
            "certificates": [],
            "projects": [],
            "unknowns": [],
        }

        mock_save_ai.assert_has_calls(
            [
                call("QA.pdf", expected_qa_profile),
                call("Designer.pdf", expected_designer_profile),
            ]
        )

    @patch("src.cv_service.save_ai_profile")
    @patch("src.cv_service.extract_ai_profile")
    @patch("src.cv_service.save_cv_profile")
    @patch("src.cv_service.build_profile")
    @patch("src.cv_service.discover_cv_files")
    def test_continues_after_one_cv_fails(
        self,
        mock_discover,
        mock_build,
        mock_save_cv,
        mock_extract_ai,
        mock_save_ai,
    ):
        mock_discover.return_value = [
            Path("Broken.pdf"),
            Path("QA.pdf"),
        ]

        mock_build.side_effect = [
            ValueError("Could not read PDF"),
            {
                "source_file": "QA.pdf",
                "raw_text": "QA Engineer with Python experience.",
            },
        ]

        mock_extract_ai.return_value = {
            "skills": ["Python"],
            "languages": [],
            "experience": [],
            "education": [],
            "certificates": [],
            "projects": [],
            "unknowns": [],
        }

        saved_count = process_all_cvs()

        self.assertEqual(saved_count, 1)
        mock_save_cv.assert_called_once()
        mock_extract_ai.assert_called_once()
        mock_save_ai.assert_called_once_with(
            "QA.pdf",
            mock_extract_ai.return_value,
        )

    @patch("src.cv_service.save_ai_profile")
    @patch("src.cv_service.extract_ai_profile")
    @patch("src.cv_service.save_cv_profile")
    @patch("src.cv_service.build_profile")
    @patch("src.cv_service.discover_cv_files")
    def test_continues_after_ollama_fails(
        self,
        mock_discover,
        mock_build,
        mock_save_cv,
        mock_extract_ai,
        mock_save_ai,
    ):
        cv_files = [
            Path("First.pdf"),
            Path("Second.pdf"),
        ]

        mock_discover.return_value = cv_files

        def build_profile_for_file(path):
            return {
                "source_file": path.name,
                "raw_text": f"Synthetic CV text for {path.name}",
            }

        mock_build.side_effect = build_profile_for_file

        valid_ai_profile = {
            "skills": ["Python"],
            "languages": [],
            "experience": [],
            "education": [],
            "certificates": [],
            "projects": [],
            "unknowns": [],
        }

        mock_extract_ai.side_effect = [
            RuntimeError("Synthetic Ollama error"),
            valid_ai_profile,
        ]

        saved_count = process_all_cvs()

        # Both source records were saved, even though Ollama failed once.
        self.assertEqual(saved_count, 2)
        self.assertEqual(mock_save_cv.call_count, 2)
        self.assertEqual(mock_extract_ai.call_count, 2)

        # Only the successful AI profile should be saved.
        mock_save_ai.assert_called_once_with(
            "Second.pdf",
            valid_ai_profile,
        )

    @patch("src.cv_service.save_ai_profile")
    @patch("src.cv_service.extract_ai_profile")
    @patch("src.cv_service.save_cv_profile")
    @patch("src.cv_service.build_profile")
    @patch("src.cv_service.discover_cv_files")
    def test_ai_receives_raw_cv_text(
        self,
        mock_discover,
        mock_build,
        mock_save_cv,
        mock_extract_ai,
        mock_save_ai,
    ):
        raw_text = (
            "Electrical technician with experience in diagnostics "
            "and electronic component replacement."
        )

        ai_profile = {
            "skills": [
                "Electronic diagnostics",
                "Component replacement",
            ],
            "languages": [
                {"name": "Polish", "level": "B2"},
            ],
            "experience": [],
            "education": [],
            "certificates": [],
            "projects": [],
            "unknowns": [],
        }

        mock_discover.return_value = [Path("Electronics.pdf")]
        mock_build.return_value = {
            "source_file": "Electronics.pdf",
            "raw_text": raw_text,
        }
        mock_extract_ai.return_value = ai_profile

        saved_count = process_all_cvs()

        self.assertEqual(saved_count, 1)
        mock_extract_ai.assert_called_once_with(raw_text)
        mock_save_ai.assert_called_once_with(
            "Electronics.pdf",
            ai_profile,
        )


if __name__ == "__main__":
    unittest.main()
