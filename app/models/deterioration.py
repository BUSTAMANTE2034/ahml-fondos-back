"""
Deterioration model for AHML Fondos application.

Defines the catalog of deterioration records/types that can be associated
to documentary records (expedientes) to describe their physical condition.
"""

from app.extensions import db


class Deterioration(db.Model):
    """Represents a deterioration record/type in the system.

    Attributes:
        id (int): Unique identifier of the deterioration record.
        user_id (int): Identifier of the user who created/updated this record.
        name (str): Current name of the deterioration type/affected entity.
        description (str): Detailed description of the deterioration observed.
        created_at (datetime): Timestamp when the deterioration record was created.
        updated_at (datetime): Timestamp when the deterioration record was last updated.
        deleted_at (datetime): Logical deletion timestamp (if the record was soft-deleted).
    """

    __tablename__ = "deterioration"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # quién lo registró
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

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

    # relación inversa
    user = db.relationship("User", backref="deteriorations", lazy=True)

    def __repr__(self):
        return f"<Deterioration {self.id}: {self.name}>"

    def to_json(self):
        """Serialize the deterioration record to a JSON-friendly dict."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
