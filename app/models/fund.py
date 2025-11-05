"""
Fund model for AHML Fondos application.

Defines the database model for documentary funds.
Includes catalog linkage, ownership (user), validity dates and audit fields.
"""

from datetime import datetime, timezone
from app.extensions import db


class Fund(db.Model):
    """Represents a documentary fund in the AHML Fondos system.

    Attributes:
        id (int): Unique identifier of the fund.
        catalog_key_id (int): Identifier of the related catalog key (catalog_key.id).
        user_id (int): Identifier of the user who created or last modified the fund.
        name (str): Full name of the fund (e.g., "Presidencia Municipal").
        acronym (str): Official acronym or abbreviation of the fund.
        start_date (date): Start date of the current name/acronym validity.
        end_date (date): End date of the current name/acronym validity.
        is_active (bool): Indicates whether the fund is currently active/visible.
        created_at (datetime): Timestamp when the fund record was created.
        updated_at (datetime): Timestamp when the fund record was last updated.
        deleted_at (datetime): Timestamp of logical deletion (if the record was soft-deleted).
    """

    __tablename__ = "fund"

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

    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

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
    catalog_key = db.relationship("CatalogKey", backref="funds", lazy=True)
    user = db.relationship("User", backref="funds", lazy=True)

    def __repr__(self):
        return f"<Fund {self.id}: {self.name}>"

    def to_json(self):
        """Serialize the fund to a JSON-friendly dict."""
        return {
            "id": self.id,
            "catalog_key_id": self.catalog_key_id,
            "user_id": self.user_id,
            "name": self.name,
            "acronym": self.acronym,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
