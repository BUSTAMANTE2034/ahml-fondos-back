"""Health schemas for request/response validation.

This module defines schemas for validating health-check API requests and responses.
"""

from marshmallow import Schema, fields


class HealthCheckSchema(Schema):
    """Schema for health-check requests."""

    message = fields.Str(required=True)
