"""
Flask Application Entry Point

Initializes and runs the Flask application with clean startup and logging.
"""

import os
import logging
from app import create_app
from app.config import Config

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def initialize_app():
    """Initialize the Flask application with configuration and logging."""
    logger.info("🚀 Starting Flask Application...")
    logger.info(f"   Environment: {Config.FLASK_ENV}")
    logger.info(f"   Debug Mode: {Config.DEBUG}")
    logger.info(f"   Database: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    logger.info("")

    # Create the Flask application
    app = create_app()

    # Optionally preload internal services (like PDF generators, etc.)
    preload_services = os.getenv("PRELOAD_SERVICES", "false").lower() == "true"
    if preload_services and not Config.DEBUG:
        logger.info("🔄 Preloading internal services (production mode)...")
        try:
            # Example: preload internal logic (optional)
            from app.services import pdf_service
            pdf_service.initialize_pdf_resources()
            logger.info(" Internal services preloaded successfully")
        except Exception as e:
            logger.warning(f" Failed to preload services: {e}")
            logger.info("Services will be loaded lazily on first request")
    else:
        logger.info("Services will be loaded lazily on first request")

    return app


# -----------------------------------------------------------------------------
# Application Creation
# -----------------------------------------------------------------------------

app = initialize_app()

# -----------------------------------------------------------------------------
# Application Run

# -----------------------------------------------------------------------------
if __name__ == "__main__":
    debug_mode = Config.DEBUG
    host = "0.0.0.0"
    port = int(os.getenv("PORT", 5000))

    if debug_mode:
        logger.info("Running in development mode (no auto-reload)")
        app.run(
            debug=True,
            host=host,
            port=port,
            use_reloader=False,  # avoids double execution on Windows
            threaded=True
        )
    else:
        logger.info(" Running in production mode")
        app.run(
            debug=False,
            host=host,
            port=port,
            threaded=True
        )
