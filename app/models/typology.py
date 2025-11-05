"""
Typology model for AHML Fondos application.

Defines documentary typologies that can be associated to record files (expedientes).
Stores name, description, creator user and audit timestamps.
"""

from datetime import datetime, timezone
from app.extensions import db


class Typology(db.Model):
    """Represents a documentary typology in the system.

    Attributes:
        id (int): Unique identifier of the typology record.
        user_id (int): Identifier of the user who created/updated this typology.
        name (str): Name of the typology or associated classification.
        description (str): Detailed description of the documentary typology.
        created_at (datetime): Timestamp when the typology was created.
        updated_at (datetime): Timestamp when the typology was last updated.
        deleted_at (datetime): Logical deletion timestamp (if the record was soft-deleted).
    """

    __tablename__ = "typology"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # quién registró esta tipología
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deleted_at = db.Column(db.DateTime, nullable=True)

    # relations
    user = db.relationship("User", backref="typologies", lazy=True)

    def __repr__(self):
        return f"<Typology {self.id}: {self.name}>"

    def to_json(self):
        """Serialize the typology to a JSON-friendly dict."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
