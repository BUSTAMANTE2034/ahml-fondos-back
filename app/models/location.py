"""
Location model for AHML Fondos application.

Defines the physical locations where record files (expedientes) can be stored.
Includes basic identification, audit timestamps and the user who created/updated it.
"""

from app.extensions import db


class Location(db.Model):
    """Represents a physical/archive location in the AHML Fondos system.

    Attributes:
        id (int): Unique identifier of the location.
        name (str): Name of the area/building/section (e.g. "Archivo", "Aguas", "Abastos").
        created_at (datetime): Timestamp when the location was created/enabled.
        updated_at (datetime): Timestamp when the location was last updated.
        deleted_at (datetime): Logical deletion timestamp (if the location was soft-deleted).
        user_id (int): Identifier of the user who created or last updated the location.
    """

    __tablename__ = "location"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    name = db.Column(db.String(255), nullable=False)

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

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    # relations
    user = db.relationship("User", backref="locations", lazy=True)

    def __repr__(self):
        return f"<Location {self.id}: {self.name}>"

    def to_json(self):
        """Serialize the location to a JSON-friendly dict."""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "user_id": self.user_id,
        }
