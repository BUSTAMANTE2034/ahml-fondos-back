"""Command-line interface commands for the application.

This module defines custom CLI commands and Flask-Migrate integration.
"""

from flask import Flask
from flask.cli import AppGroup

from app.extensions import db, migrate


def init_cli(app: Flask) -> None:
    """Initialize CLI commands and migrations.

    Args:
        app: Flask application instance
    """
    # Initialize Flask-Migrate with the application and database
    migrate.init_app(app, db)

    # Create custom command groups
    db_cli = AppGroup("db-ops", help="Database operations")

    # Register command groups with the application
    app.cli.add_command(db_cli)

    # Define custom database commands
    @db_cli.command("recreate")
    def recreate_db() -> None:
        """Drop all tables and recreate them."""
        db.drop_all()
        db.create_all()
        print("Database tables dropped and recreated successfully!")
