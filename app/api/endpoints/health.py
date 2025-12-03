"""Health check API endpoints.

This module defines endpoints for health monitoring and status checks.
"""

from flask_restx import Namespace, Resource
from marshmallow import ValidationError

from app.schemas.health import HealthCheckSchema

# Create a namespace
api = Namespace('health', description='Health check operations')

@api.route('/')
class HealthCheck(Resource):
    """Health check endpoint resource.

    Provides a simple endpoint to verify API availability.
    """

    def get(self):
        """Handle GET request.

        Returns:
            dict: Status response
        """
        try:
            return HealthCheckSchema().dump({"message": "OK"}), 200
        except ValidationError as err:
            return {"message": "Validation error", "errors": err.messages}, 400
