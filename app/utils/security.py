"""Security utilities for AHML Fondos Services.

This module provides security related utilities for authentication and authorization.
"""

from functools import wraps
from flask import abort
from flask_login import current_user

from app.extensions import bcrypt, db, login_manager
from app.models.user import User
from app.config import Config
from typing import Optional

import string
import random

def generate_temp_password(length: int = 10) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))

def role_required(*allowed_roles):
    """Decorator to restrict access to users with one of the specified roles.

    Args:
        *allowed_roles: One or more roles allowed to access the route

    Returns:
        Function: Decorated function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def create_superadmin() -> None:
    """Create a Admin user from configuration."""

    # Use a public method or attribute instead of accessing protected member
    admin_config = Config.get_config().get("ADMIN", {})
    admin_email = admin_config.get("EMAIL")

    if not admin_email:
        print("No admin email configured, skipping admin creation")
        return

    user = User.query.filter_by(email=admin_email).first()
    if user:
        print("Admin user already exists!")
        return

    admin_user = User(
        email=admin_email,
        password=bcrypt.generate_password_hash(admin_config.get("PASSWORD")).decode(
            "utf-8"
        ),
        first_name=admin_config.get("FIRST_NAME"),
        last_name=admin_config.get("LAST_NAME"),
        employee_id="000000",
        first_login=False,
        is_active=True,
        role="admin",
    )
    db.session.add(admin_user)
    db.session.commit()
    print("Admin user created successfully!")


@login_manager.user_loader
def load_user(user_id: int) -> Optional[User]:
    """Load a user from the database using the user_id.

    This is a callback function used by Flask-Login to retrieve a User
    object based on the user_id stored in the session.

    Args:
        user_id: The ID of the user to load from the database

    Returns:
        User: The User object corresponding to the given user_id
    """
    return User.query.get(int(user_id))


"""def token_required(f):
    Decorator to handle token-based authentication for API endpoints.
    
    This complements Flask-Login's session-based auth to support API clients.
    It checks for a token in the Authorization header and authenticates the user
    if the token is valid. If no token is provided, it falls back to session auth.
    
    Args:
        f: The function to decorate
        
    Returns:
        Function: Decorated function
    
    @wraps(f)
    def decorated(*args, **kwargs):
        # If user is already authenticated via session, allow access
        if current_user.is_authenticated:
            return f(*args, **kwargs)
            
        # Check for token in Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            # Here you could implement token validation
            # For a simple example, let's assume the token is the user's ID
            user = User.query.get(int(token))
            if user:
                # Log in the user for this request
                login_user(user)
                return f(*args, **kwargs)
        
        # If no valid authentication, return 401
        return {'message': 'Authentication required'}, 401
        
    return decorated"""
