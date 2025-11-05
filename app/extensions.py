"""Flask extensions module.

This module initializes all Flask extensions used throughout the application,
ensuring they are created once and can be imported and used across all modules.
"""

from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy
db = SQLAlchemy()

# Initialize Bcrypt for password hashing
bcrypt = Bcrypt()

# Initialize LoginManager for authentication
login_manager = LoginManager()

# Initialize Flask-Migrate
migrate = Migrate()
