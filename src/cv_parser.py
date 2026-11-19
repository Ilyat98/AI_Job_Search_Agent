
from pathlib import Path

from pypdf import PdfReader

from src.config_loader import load_settings


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CV_DIRECTORY = PROJECT_ROOT / "CV"


def extract_text_from_pdf(file_path: str | Path) -> str:
    """Extract text from a PDF file."""

    path = Path(file_path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.is_file():
        raise FileNotFoundError(f"CV file not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Unsupported file format: {path.suffix}")

    reader = PdfReader(str(path))

    if reader.is_encrypted:
        raise ValueError(f"PDF is encrypted: {path.name}")

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text and text.strip():
            pages.append(text.strip())

    result = "\n\n".join(pages).strip()

    if not result:
        raise ValueError(
            f"No extractable text found in PDF: {path.name}. "
            "The document may require OCR."
        )

    return result


def extract_text_from_docx(file_path: str | Path) -> str:
    """Extract paragraphs and table text from a DOCX CV."""
    try:
        from docx import Document
    except ImportError as error:
        raise RuntimeError(
            "DOCX support requires python-docx. Install project dependencies."
        ) from error

    path = Path(file_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f"CV file not found: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Unsupported file format: {path.suffix}")

    document = Document(path)
    parts = [paragraph.text.strip() for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    result = "\n".join(part for part in parts if part).strip()
    if not result:
        raise ValueError(
            f"No extractable text found in CV: {path.name}."
        )
    return result


def extract_text_from_cv(file_path: str | Path) -> str:
    """Extract text from a configured CV format."""
    path = Path(file_path)
    extractors = {
        ".pdf": extract_text_from_pdf,
        ".docx": extract_text_from_docx,
    }
    extractor = extractors.get(path.suffix.lower())
    if extractor is None:
        raise ValueError(f"Unsupported file format: {path.suffix}")
    return extractor(path)


def configured_cv_settings() -> tuple[Path, set[str]]:
    """Return the CV folder and file extensions from application settings."""
    cv_settings = load_settings().get("cv", {})
    directory = Path(cv_settings.get("directory", "CV"))
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    extensions = {
        extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        for extension in cv_settings.get("supported_extensions", [".pdf"])
    }
    return directory, extensions


def discover_pdf_files(directory: str | Path = CV_DIRECTORY) -> list[Path]:
    """Find PDF files directly inside the CV directory."""

    directory = Path(directory)

    if not directory.is_dir():
        raise FileNotFoundError(
            f"CV directory not found: {directory}"
        )

    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def discover_cv_files(
    directory: str | Path | None = None,
    extensions: set[str] | None = None,
) -> list[Path]:
    """Find CV files in the configured directory, including newly added CVs."""
    if directory is None:
        directory, configured_extensions = configured_cv_settings()
        if extensions is None:
            extensions = configured_extensions
    if extensions is None:
        extensions = {".pdf", ".docx"}

    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"CV directory not found: {directory}")
    normalized_extensions = {item.lower() for item in extensions}
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in normalized_extensions
    )


def main() -> None:
    cv_files = discover_cv_files()

    if not cv_files:
        print("No supported CV files found in the CV directory.")
        return

    print(f"Found {len(cv_files)} supported CV file(s).\n")

    for cv_path in cv_files:
        try:
            text = extract_text_from_cv(cv_path)

            print(f"File: {cv_path.name}")
            print(f"Extracted characters: {len(text)}")
            print(f"Preview:\n{text[:300]}")
            print("-" * 50)

        except (OSError, ValueError) as error:
            print(f"Could not process {cv_path.name}: {error}")


if __name__ == "__main__":
    main()
