"""
User model for AHML Fondos application.

Defines the database model for system users and employees.
Includes authentication credentials, access roles, account status, 
and audit timestamps for creation and modification.
"""

from datetime import datetime, timezone
from flask_login import UserMixin
from app.extensions import db


class User(db.Model, UserMixin):
    """Represents a user in the AHML Fondos system.

    Attributes:
        id (int): Auto-incrementing primary key.
        employee_id (str): Unique identifier for the employee (e.g., employee number).
        first_name (str): First name of the user.
        last_name (str): Last name of the user.
        email (str): Unique email address used for authentication.
        password (str): Hashed password for login.
        is_active (bool): Indicates whether the account is active.
        role (str): Role assigned to the user (admin, manager, archivist, visitor, etc.).
        first_login (bool): Marks if it's the user's first login.
        created_at (datetime): Timestamp of account creation.
        updated_at (datetime): Timestamp of last account update.
        deleted_at (datetime): Timestamp of logical deletion (if any).
    """

    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100))
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    role = db.Column(db.String(50), nullable=False, default="visitor")
    first_login = db.Column(db.Boolean, default=True)
    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        server_onupdate=db.func.now(),
        nullable=False,
    )
    deleted_at = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        """Return a concise string representation for debugging."""
        return f"<User {self.email} ({self.employee_id}) - Role: {self.role}>"

    def to_json(self):
        """Serialize the user instance to a dictionary (JSON-compatible)."""
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "is_active": self.is_active,
            "role": self.role,
            "first_login": self.first_login,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "last_login": self.last_login,
        }
