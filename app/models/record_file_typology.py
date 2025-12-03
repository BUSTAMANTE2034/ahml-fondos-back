"""
RecordFileTypology model for AHML Fondos application.

Joins record files (expedientes) with documentary typologies.
Allows tracking when a typology was linked, updated or soft-deleted.
"""

from app.extensions import db


class RecordFileTypology(db.Model):
    """Represents the relation between a record file and a typology.

    Attributes:
        id (int): Unique identifier of the relation record.
        record_file_id (int): Identifier of the associated record file (record_file.id).
        typology_id (int): Identifier of the associated typology (typology.id).
        created_at (datetime): When the typology was linked to the record file.
        updated_at (datetime): When the relation was last updated.
        deleted_at (datetime): Logical deletion timestamp (when the relation was unlinked).
    """

    __tablename__ = "record_file_typology"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    record_file_id = db.Column(
        db.Integer,
        db.ForeignKey("record_file.id"),
        nullable=False,
    )

    typology_id = db.Column(
        db.Integer,
        db.ForeignKey("typology.id"),
        nullable=False,
    )

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
    record_file = db.relationship("RecordFile", backref="record_file_typologies", lazy=True)
    typology = db.relationship("Typology", backref="record_file_typologies", lazy=True)

    # evitar duplicados activos
    __table_args__ = (
        db.UniqueConstraint("record_file_id", "typology_id", name="uq_recordfile_typology"),
    )

    def __repr__(self):
        return f"<RecordFileTypology rf={self.record_file_id} typ={self.typology_id}>"

    def to_json(self):
        """Serialize the relation to a JSON-friendly dict."""
        return {
            "id": self.id,
            "record_file_id": self.record_file_id,
            "typology_id": self.typology_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
