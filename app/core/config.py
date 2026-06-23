"""
Centralized configuration module for the Kaizen backend.
Loads environment variables from .env (development) or .env.production (production).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Determine environment: check ENVIRONMENT variable or default to development
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

# Get the directory where this config.py file is located
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment-specific .env file
if ENVIRONMENT == "production":
    env_file = CONFIG_DIR / ".env.production"
    if not env_file.exists():
        # Fallback to .env if .env.production doesn't exist
        env_file = CONFIG_DIR / ".env"
        print(f"[WARNING] .env.production not found, falling back to .env")
else:
    env_file = CONFIG_DIR / ".env"

# Load the environment file
if env_file.exists():
    load_dotenv(env_file, override=(ENVIRONMENT != "production"))
    print(f"[CONFIG] Loaded environment from: {env_file.name} (ENVIRONMENT={ENVIRONMENT})")
else:
    print(f"[WARNING] Environment file not found: {env_file}")
    # Still try to load from default .env location
    load_dotenv()

# Database URL - REQUIRED, no fallback
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise ValueError(
        f"DB_URL environment variable is required but not set. "
        f"Please set it in {env_file.name} or as an environment variable."
    )

# Optional: Export other commonly used environment variables
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Microsoft Azure AD SSO configuration (optional)
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "")
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")

# Public frontend URL for ticket links and email logo assets
FRONTEND_PUBLIC_URL = (os.getenv("FRONTEND_PUBLIC_URL") or os.getenv("VITE_APP_URL") or "http://localhost:5173").rstrip("/")

