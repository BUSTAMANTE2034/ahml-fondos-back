"""
Flask application factory and core initialization.

This package initializes the web service application, handling:
- Flask app instance creation
- Configuration loading
- Database setup
- Blueprint registration
- Security and authentication
- Migrations management
"""

from flask import Flask
from flask_cors import CORS

from app.extensions import db, bcrypt, login_manager
from app.api import register_blueprints
from app.cli import init_cli
from app.utils.security import create_superadmin


def create_app() -> Flask:
    """Create and configure the Flask application instance.

    This factory function handles:
    - Application configuration loading
    - Database initialization
    - Blueprint registration
    - Context-bound setup tasks
    - Security and authentication setup
    - CLI commands and migrations

    Returns:
        Flask: The configured Flask application instance
    """
    # Initialize Flask app
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    # Initialize Flask extensions

    db.init_app(app)
    bcrypt.init_app(app)

    # Configure login manager
    login_manager.init_app(app)
    login_manager.session_protection = "strong"
    @login_manager.unauthorized_handler
    def unauthorized():
        # devolvemos dict, no jsonify
        return {
            "message": "No estás autenticado o tu sesión expiró.",
            "error": "unauthorized",
            "status_code": 401,
        }, 401

    # === CORS configuration ===
    # Allow requests from local development, production, and public IP
    allowed_origins = [
        "http://localhost:5173",        # Vite dev server
        "http://localhost:3000",        # React dev server alternative
        "http://189.195.96.226",        # Your public IP (HTTP)
        "https://189.195.96.226",       # Your public IP (HTTPS)
    ]

    CORS(
    app,
    origins=allowed_origins,
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    expose_headers=["Content-Disposition"],  # ←  ESTE ES EL CLAVE
)


    # Initialize CLI commands and migrations
    init_cli(app)

    # Register all API blueprints
    register_blueprints(app)

    # Error handler for 404
    @app.errorhandler(404)
    def not_found_error(error: Exception) -> tuple[dict, int]:
        """Handle 404 errors and return a JSON response."""
        return {
            "message": str(error),
            "error": "Recurso no encontrado",
            "status_code": 404,
        }, 404

    # Database setup and default superadmin creation
    # with app.app_context():
    #     # db.create_all()
    #     create_superadmin()

    return app
