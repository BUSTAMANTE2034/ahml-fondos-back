"""
Series model for AHML Fondos.

Represents a documentary series inside a fund.
Links to catalog keys, funds, and the user who created/updated it.
"""

from datetime import datetime, timezone, date
from app.extensions import db


class Series(db.Model):
    """Represents a documentary series.

    Attributes:
        id (int): Unique identifier for the series.
        catalog_key_id (int): FK to catalog_key.id (the catalog’s key this series uses).
        fund_id (int): FK to fund.id (the fund this series belongs to).
        user_id (int): FK to user.id (who created/updated it).
        name (str): Name of the documentary series.
        acronym (str): Short code / acronym.
        start_date (date): Start of validity of this name/acronym.
        end_date (date): End of validity (if it changed).
        is_active (bool): Whether this series is currently in use.
        created_at (datetime): When it was created.
        updated_at (datetime): When it was last updated.
        deleted_at (datetime): Logical deletion timestamp (nullable).
    """

    __tablename__ = "series"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # FK to catalog key (optional if you still don’t have the table)
    catalog_key_id = db.Column(
        db.Integer,
        db.ForeignKey("catalog_key.id"),
        nullable=True,
    )

    # # FK to fund
    # fund_id = db.Column(
    #     db.Integer,
    #     db.ForeignKey("fund.id"),
    #     nullable=True,
    # )

    # FK to user (who registered/modified)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    name = db.Column(db.String(255), nullable=False)
    acronym = db.Column(db.String(50), nullable=True)

    # validity dates for the current name/acronym
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

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

    # relations
    catalog_key = db.relationship("CatalogKey", backref="series", lazy=True)
    # fund = db.relationship("Fund", backref="series", lazy=True)
    user = db.relationship("User", backref="series", lazy=True)

    def __repr__(self) -> str:
        return f"<Series {self.id}: {self.name} ({'active' if self.is_active else 'inactive'})>"

    def to_json(self) -> dict:
        """Serialize the series to JSON."""
        return {
            "id": self.id,
            "catalog_key_id": self.catalog_key_id,
            "fund_id": self.fund_id,
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
