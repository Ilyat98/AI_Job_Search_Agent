
import logging
from pathlib import Path
from typing import Any

from src.cv_parser import (
    discover_cv_files,
    extract_text_from_docx,
    extract_text_from_pdf,
)


logger = logging.getLogger(__name__)


def build_profile(file_path: str | Path) -> dict[str, Any]:
    """
    Extract raw text from a supported CV document.

    Professional information is extracted by the AI profile extractor.
    This function does not use predefined lists, keywords or regex
    patterns to identify facts about the candidate.
    """
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        text = extract_text_from_pdf(path)
    elif path.suffix.lower() == ".docx":
        text = extract_text_from_docx(path)
    else:
        raise ValueError(f"Unsupported CV format: {path.suffix}")

    if not text.strip():
        raise ValueError(
            f"No readable text found in CV '{path.name}'."
        )

    return {
        "source_file": path.name,
        "raw_text": text,
    }


def build_profiles(
    directory: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Extract raw text from all readable supported CVs in a directory."""
    profiles = []

    for cv_path in discover_cv_files(directory):
        try:
            profile = build_profile(cv_path)
            profiles.append(profile)

            logger.info(
                "Extracted text from CV '%s'.",
                cv_path.name,
            )

        except (OSError, ValueError):
            logger.exception(
                "Could not process CV '%s'.",
                cv_path.name,
            )

    return profiles


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    profiles = build_profiles()

    print(f"Successfully processed {len(profiles)} CV(s).\n")

    for profile in profiles:
        print("=" * 60)
        print("CV:", profile["source_file"])
        print("Extracted text length:", len(profile["raw_text"]))
        print("Professional facts: not extracted in this module")

    if not profiles:
        print("No readable CV profiles were created.")


if __name__ == "__main__":
    main()
