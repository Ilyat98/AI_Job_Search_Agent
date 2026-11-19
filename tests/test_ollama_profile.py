
import json

from src.ai_profile_extractor import extract_ai_profile
from src.cv_parser import discover_pdf_files, extract_text_from_pdf


def main() -> None:
    cv_files = discover_pdf_files()

    if not cv_files:
        raise RuntimeError("No PDF CVs were found in the CV folder.")

    # Use the first CV by file name.
    cv_path = cv_files[0]

    print(f"Testing CV: {cv_path.name}")

    text = extract_text_from_pdf(cv_path)
    print(f"Extracted characters: {len(text)}")

    profile = extract_ai_profile(text)

    print("\nAI profile:")
    print(json.dumps(profile, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
