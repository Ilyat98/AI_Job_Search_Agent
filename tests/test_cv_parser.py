
import tempfile
import unittest
from pathlib import Path

from src.cv_parser import discover_cv_files, discover_pdf_files, extract_text_from_pdf


class TestCVParser(unittest.TestCase):

    def test_discovers_multiple_pdf_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)

            (directory / "QA Engineer.pdf").touch()
            (directory / "Junior AQA.PDF").touch()
            (directory / "notes.txt").touch()

            files = discover_pdf_files(directory)

            self.assertEqual(len(files), 2)
            self.assertEqual(
                {path.name for path in files},
                {"QA Engineer.pdf", "Junior AQA.PDF"},
            )

    def test_discovers_configured_pdf_and_docx_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "QA.pdf").touch()
            (directory / "Polish CV.docx").touch()
            (directory / "notes.txt").touch()

            files = discover_cv_files(directory)

            self.assertEqual(
                {path.name for path in files},
                {"QA.pdf", "Polish CV.docx"},
            )

    def test_missing_pdf_raises_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_file = Path(temp_dir) / "missing.pdf"

            with self.assertRaises(FileNotFoundError):
                extract_text_from_pdf(missing_file)

    def test_unsupported_extension_raises_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            text_file = Path(temp_dir) / "resume.txt"
            text_file.touch()

            with self.assertRaises(ValueError):
                extract_text_from_pdf(text_file)


if __name__ == "__main__":
    unittest.main()
