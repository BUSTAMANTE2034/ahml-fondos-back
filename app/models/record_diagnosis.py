"""
RecordDiagnosis model for AHML Fondos application.

Represents a technical revision of a record file.
A revision may be associated with multiple diagnostic catalog entries.
"""

from app.extensions import db
from app.models.record_diagnosis_catalog import record_diagnosis_catalog


class RecordDiagnosis(db.Model):
    __tablename__ = "record_diagnosis"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    record_file_id = db.Column(
        db.Integer,
        db.ForeignKey("record_file.id"),
        nullable=False,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    revision_date = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False,
    )

    observations = db.Column(db.Text, nullable=True)

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

    # relaciones
    record_file = db.relationship("RecordFile", backref="revisions", lazy=True)
    user = db.relationship("User", lazy=True)

    diagnosis_catalog = db.relationship(
        "DiagnosisCatalog",
        secondary=record_diagnosis_catalog,
        lazy="subquery",
        backref=db.backref("record_diagnoses", lazy=True),
    )

    def __repr__(self):
        return f"<RecordDiagnosis {self.id} - RecordFile {self.record_file_id}>"

    def to_json(self):
        return {
            "id": self.id,
            "record_file_id": self.record_file_id,
            "user_id": self.user_id,
            "revision_date": self.revision_date,
            "observations": self.observations,
            "diagnosis_catalog_ids": [
                dc.id for dc in self.diagnosis_catalog
            ],
        }
