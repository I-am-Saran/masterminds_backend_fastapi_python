"""
Start the FastAPI backend.

Usage:
    python start_app.py dev     # auto-reload on code changes (quiet terminal)
    python start_app.py prod    # no reload, for stable runs
"""

import argparse
import logging
import os
import sys

import psycopg2

# Ensure the project root is on the Python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

HOST = os.getenv("APP_HOST", "127.0.0.1")
PORT = int(os.getenv("APP_PORT", "8000"))

# Only watch application source — avoids reload loops from logs, venv, backups, etc.
RELOAD_DIRS = [
    os.path.join(ROOT_DIR, "app"),
    os.path.join(ROOT_DIR, "services"),
    os.path.join(ROOT_DIR, "utils"),
    ROOT_DIR,  # main.py, config.py at project root
]

RELOAD_EXCLUDES = [
    "*.log",
    "*.sql",
    "*.md",
    "*.pyc",
    "__pycache__",
    "venv",
    "logs",
    "scripts",
    ".git",
    ".env",
    ".env.*",
]


def configure_quiet_logging() -> None:
    """Reduce noisy reload / access log spam in the dev terminal."""
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def verify_database_connection() -> None:
    from config import DB_URL

    try:
        conn = psycopg2.connect(DB_URL)
        conn.close()
        print("[OK] Database connection successful")
    except Exception as exc:
        print(f"[ERROR] Database connection failed: {exc}")
        print(
            "Fix DB_URL in .env, ensure PostgreSQL is running, then run:\n"
            "  bash scripts/db/setup_local_dev_db.sh"
        )
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the Kaizen FastAPI backend")
    parser.add_argument(
        "mode",
        nargs="?",
        default="dev",
        choices=("dev", "prod"),
        help="dev = reload on code changes; prod = no reload",
    )
    return parser.parse_args()


def main() -> None:
    import uvicorn

    args = parse_args()
    reload = args.mode == "dev"

    configure_quiet_logging()
    verify_database_connection()

    print(f"Starting server ({args.mode}) at http://{HOST}:{PORT}")

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=reload,
        reload_dirs=RELOAD_DIRS if reload else None,
        reload_excludes=RELOAD_EXCLUDES if reload else None,
        log_level="info",
        access_log=not reload,
    )


if __name__ == "__main__":
    main()
