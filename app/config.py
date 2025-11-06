import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _get_bool_env(key: str, default: bool = False) -> bool:
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def _validate_config():
    warnings = []
    if not os.getenv("SECRET_KEY"):
        warnings.append("SECRET_KEY is not set")
    if not os.getenv("DB_PASSWORD"):
        warnings.append("DB_PASSWORD is not set")
    if warnings:
        logger.warning("Configuration warnings:")
        for w in warnings:
            logger.warning("  - %s", w)


class Config:
    """Base configuration class for Flask + MySQL."""

    FLASK_ENV = os.getenv("FLASK_ENV")
    SECRET_KEY = os.getenv("SECRET_KEY")
    DEBUG = _get_bool_env("DEBUG", True)

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_pre_ping": True,
    "pool_recycle": 28000,
}

    # si quieres bajar costo de bcrypt para dev
    BCRYPT_LOG_ROUNDS = 4

    # DB
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME", "mydatabase")

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    # admin inicial
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    ADMIN_FIRST_NAME = os.getenv("ADMIN_FIRST_NAME")
    ADMIN_LAST_NAME = os.getenv("ADMIN_LAST_NAME")

    # mail
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 465))
    MAIL_USE_TLS = _get_bool_env("MAIL_USE_TLS", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", MAIL_USERNAME)
    MAIL_DEFAULT_NAME = os.getenv("MAIL_DEFAULT_NAME", "Sistema AHML")

    @classmethod
    def get_config(cls) -> dict:
        return {
            "SECRET_KEY": cls.SECRET_KEY,
            "DEBUG": cls.DEBUG,
            "FLASK_ENV": cls.FLASK_ENV,
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
            "MAIL": {
                "SERVER": cls.MAIL_SERVER,
                "PORT": cls.MAIL_PORT,
                "USERNAME": cls.MAIL_USERNAME,
                "DEFAULT_SENDER": cls.MAIL_DEFAULT_SENDER,
            },
        }

    @classmethod
    def validate_and_log(cls):
        _validate_config()
        logger.info("Configuration loaded successfully:")
        logger.info("  - DEBUG: %s", cls.DEBUG)
        logger.info("  - Database: %s:%s/%s", cls.DB_HOST, cls.DB_PORT, cls.DB_NAME)
        logger.info("  - Mail server: %s:%s", cls.MAIL_SERVER, cls.MAIL_PORT)


_validate_config()
