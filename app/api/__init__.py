"""
API module initialization for AHML Fondos.

This module handles the registration of all API blueprints with the Flask application.
"""

from flask import Blueprint
from flask_restx import Api

# Import namespaces (tus endpoints reales)

from app.api.endpoints.health import api as health
from app.api.endpoints.auth import api as auth
from app.api.endpoints.users import api as users
from app.api.endpoints.catalog_keys import api as catalog_keys
from app.api.endpoints.funds import api as funds
from app.api.endpoints.sections import api as sections
from app.api.endpoints.series import api as series


# Crear instancia principal de API y Blueprint
api_blueprint = Blueprint("api", __name__, url_prefix="/")

api = Api(
    api_blueprint,
    title="AHML Fondos API",
    version="1.0",
    description="API de Servicios AHML Fondos — Gestión de archivos, fondos y conversaciones.",
)

# Registrar todos los namespaces (módulos de endpoints)

api.add_namespace(health)
api.add_namespace(auth)
api.add_namespace(users)
api.add_namespace(catalog_keys)
api.add_namespace(funds)
api.add_namespace(sections)
api.add_namespace(series)


# Función para registrar el blueprint en la aplicación Flask
def register_blueprints(app):
    """Register the API blueprint with the Flask application.

    Args:
        app: The Flask application instance
    """
    app.register_blueprint(api_blueprint)
    
