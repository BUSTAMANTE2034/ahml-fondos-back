"""
Configuration settings using environment variables for Flask + MySQL

This module handles:
- Environment variable loading with python-dotenv
- Configuration validation and warnings
- Database URI construction for MySQL
"""

import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


def _get_bool_env(key: str, default: bool = False) -> bool:
    """Convert environment variable to boolean."""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def _validate_config():
    """Validate configuration for security and completeness."""
    warnings = []

    # Check for secret key
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        warnings.append("SECRET_KEY is not set")

    # Check for database password
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        warnings.append("DB_PASSWORD is not set")

    if warnings:
        logger.warning("Configuration warnings:")
        for warning in warnings:
            logger.warning("  - %s", warning)


class Config:
    """Base configuration class for Flask + MySQL."""

    # General Flask settings
    FLASK_ENV =os.getenv("FLASK_ENV")
    SECRET_KEY = os.getenv("SECRET_KEY")
    DEBUG = _get_bool_env("DEBUG", True)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database settings (MySQL)
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME", "mydatabase")
    
    # Admin user configuration (for initial setup)
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    ADMIN_FIRST_NAME = os.getenv("ADMIN_FIRST_NAME")
    ADMIN_LAST_NAME = os.getenv("ADMIN_LAST_NAME")

    # SQLAlchemy connection URI
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    @classmethod
    def get_config(cls) -> dict:
        """Return configuration as dictionary."""
        return {
            "SECRET_KEY": cls.SECRET_KEY,
            "DEBUG": cls.DEBUG,
            "FLASK_ENV":cls.FLASK_ENV,
            "DATABASE": {
                "ENGINE": "mysql",
                "URI": cls.SQLALCHEMY_DATABASE_URI,
                "USER": cls.DB_USER,
                "PASSWORD": cls.DB_PASSWORD,
                "HOST": cls.DB_HOST,
                "PORT": cls.DB_PORT,
                "NAME": cls.DB_NAME,
            },
             "ADMIN": {
                "EMAIL": cls.ADMIN_EMAIL,
                "PASSWORD": cls.ADMIN_PASSWORD,
                "FIRST_NAME": cls.ADMIN_FIRST_NAME,
                "LAST_NAME": cls.ADMIN_LAST_NAME,
            },
        }

    @classmethod
    def validate_and_log(cls):
        """Validate configuration and log summary."""
        _validate_config()
        logger.info("Configuration loaded successfully:")
        logger.info("  - DEBUG: %s", cls.DEBUG)
        logger.info(
            "  - Database: %s:%s/%s",
            cls.DB_HOST,
            cls.DB_PORT,
            cls.DB_NAME,
        )


# Validate configuration when imported
_validate_config()
