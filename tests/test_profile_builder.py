
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.profile_builder import build_profile, build_profiles


class TestProfileBuilder(unittest.TestCase):

    def test_builds_profile_with_raw_text(self):
        expected_text = (
            "QA Engineer with Python, Pytest and SQL experience."
        )

        with patch(
            "src.profile_builder.extract_text_from_pdf",
            return_value=expected_text,
        ):
            profile = build_profile("QA.pdf")

        self.assertEqual(profile["source_file"], "QA.pdf")
        self.assertEqual(profile["raw_text"], expected_text)

        # Professional facts are extracted by AI, not here.
        self.assertNotIn("skills", profile)
        self.assertNotIn("languages", profile)
        self.assertNotIn("job_titles", profile)
        self.assertNotIn("sections", profile)

    def test_builds_profile_from_docx(self):
        with patch(
            "src.profile_builder.extract_text_from_docx",
            return_value="Polish CV with QA experience.",
        ):
            profile = build_profile("Polish CV.docx")

        self.assertEqual(profile["source_file"], "Polish CV.docx")
        self.assertEqual(profile["raw_text"], "Polish CV with QA experience.")

    def test_builds_separate_profiles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)

            (directory / "QA.pdf").touch()
            (directory / "Designer.pdf").touch()

            def fake_extract(path):
                if Path(path).name == "QA.pdf":
                    return "Python, Pytest and functional testing."
                return "Unity game design."

            with patch(
                "src.profile_builder.extract_text_from_pdf",
                side_effect=fake_extract,
            ):
                profiles = build_profiles(directory)

        self.assertEqual(len(profiles), 2)

        profiles_by_name = {
            profile["source_file"]: profile
            for profile in profiles
        }

        self.assertEqual(
            profiles_by_name["QA.pdf"]["raw_text"],
            "Python, Pytest and functional testing.",
        )
        self.assertEqual(
            profiles_by_name["Designer.pdf"]["raw_text"],
            "Unity game design.",
        )

    def test_rejects_empty_extracted_text(self):
        with patch(
            "src.profile_builder.extract_text_from_pdf",
            return_value="   \n ",
        ):
            with self.assertRaises(ValueError):
                build_profile("Empty.pdf")

    def test_build_profiles_continues_after_invalid_pdf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)

            (directory / "Broken.pdf").touch()
            (directory / "Valid.pdf").touch()

            def fake_extract(path):
                if Path(path).name == "Broken.pdf":
                    raise ValueError("Could not extract PDF text")

                return "Valid CV text."

            with patch(
                "src.profile_builder.extract_text_from_pdf",
                side_effect=fake_extract,
            ):
                profiles = build_profiles(directory)

        self.assertEqual(len(profiles), 1)
        self.assertEqual(
            profiles[0]["source_file"],
            "Valid.pdf",
        )
        self.assertEqual(
            profiles[0]["raw_text"],
            "Valid CV text.",
        )

    def test_rejects_pdf_with_extraction_error(self):
        with patch(
            "src.profile_builder.extract_text_from_pdf",
            side_effect=OSError("File cannot be read"),
        ):
            with self.assertRaises(OSError):
                build_profile("Unreadable.pdf")


if __name__ == "__main__":
    unittest.main()
