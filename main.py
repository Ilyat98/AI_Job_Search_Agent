
from src.config_loader import load_settings
from src.database import (
    DATABASE_PATH,
    count_jobs,
    init_db,
    is_initial_search,
)


def main() -> None:
    settings = load_settings()

    init_db()

    print("AI Job Search Agent")
    print("Configuration loaded successfully.")
    print("Database initialized successfully.")
    print("Database path:", DATABASE_PATH)
    print("Stored vacancies:", count_jobs())

    if is_initial_search():
        print("Search state: initial search is pending.")
    else:
        print("Search state: initial search has been completed.")

    print("Timezone:", settings["app"]["timezone"])


if __name__ == "__main__":
    main()