"""
CatalogKey model for AHML Fondos application.

Defines reusable catalog keys that can be linked to funds, sections or series.
Stores the code, name, description, owner user, status and audit timestamps.
"""

from datetime import datetime, timezone
from app.extensions import db


class CatalogKey(db.Model):
    """Represents a catalog key that can be assigned to archival entities.

    Attributes:
        id (int): Unique identifier of the catalog key.
        user_id (int): Identifier of the user who created or last modified the key.
        entity_type (str): Type of entity this key belongs to (e.g. 'fund', 'section', 'series').
        key (str): Unique catalog code (e.g. "PML-PRM-1935").
        name (str): Descriptive name or title for the key.
        description (str): Additional description, purpose or historical context.
        is_active (bool): Indicates whether the key is currently active / in use.
        created_at (datetime): When the key was created.
        updated_at (datetime): When the key was last updated.
        deleted_at (datetime): Logical deletion timestamp (if soft-deleted).
    """

    __tablename__ = "catalog_key"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    # 'fund' / 'section' / 'series' (lo dejamos libre por ahora)
    entity_type = db.Column(db.String(50), nullable=False)

    # clave única del catálogo
    key = db.Column(db.String(255), unique=True, nullable=False)

    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

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
    user = db.relationship("User", backref="catalog_keys", lazy=True)

    def __repr__(self):
        return f"<CatalogKey {self.id}: {self.key} ({self.entity_type})>"

    def to_json(self):
        """Serialize the catalog key to a JSON-friendly dict."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "entity_type": self.entity_type,
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
