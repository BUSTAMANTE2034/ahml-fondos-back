"""
Section model for AHML Fondos application.

Defines the database model for administrative/organizational sections.
Includes catalog linkage, owner user, validity dates and audit fields.
"""

from datetime import datetime, timezone
from app.extensions import db


class Section(db.Model):
    """Represents an administrative/organizational section in the AHML Fondos system.

    Attributes:
        id (int): Unique identifier of the section.
        catalog_key_id (int): Identifier of the related catalog key (catalog_key.id).
        user_id (int): Identifier of the user who created or last updated the section.
        name (str): Full name of the section/area (e.g. "Secretaría del Ayuntamiento").
        acronym (str): Official acronym or short name of the section.
        created_at (datetime): Timestamp when the section record was created.
        start_date (date): Start date of the current name/acronym validity.
        end_date (date): End date of the current name/acronym validity.
        is_active (bool): Indicates whether the section is currently active/in use.
        updated_at (datetime): Timestamp when the section was last updated.
        deleted_at (datetime): Timestamp of logical deletion (soft delete), if any.
    """

    __tablename__ = "section"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    catalog_key_id = db.Column(
        db.Integer,
        db.ForeignKey("catalog_key.id"),
        nullable=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    name = db.Column(db.String(255), nullable=False)
    acronym = db.Column(db.String(50), nullable=True)

    # audit + validity
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deleted_at = db.Column(db.DateTime, nullable=True)

    # relations
    catalog_key = db.relationship("CatalogKey", backref="sections", lazy=True)
    user = db.relationship("User", backref="sections", lazy=True)

    def __repr__(self):
        return f"<Section {self.id}: {self.name}>"

    def to_json(self):
        """Serialize the section to a JSON-friendly dict."""
        return {
            "id": self.id,
            "catalog_key_id": self.catalog_key_id,
            "user_id": self.user_id,
            "name": self.name,
            "acronym": self.acronym,
            "created_at": self.created_at,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "is_active": self.is_active,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
