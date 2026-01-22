"""
DiagnosisCatalog model for AHML Fondos application.

Defines the catalog of diagnostic concepts and details used during
technical revision of record files.
"""

from app.extensions import db


class DiagnosisCatalog(db.Model):
    __tablename__ = "diagnosis_catalog"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    concept = db.Column(db.String(255), nullable=False)
    detail = db.Column(db.String(255), nullable=False)

    description = db.Column(db.Text, nullable=True)

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
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    
    deleted_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship("User", lazy=True)
    def __repr__(self):
        return f"<DiagnosisCatalog {self.id}: {self.concept} / {self.detail}>"

    def to_json(self):
        return {
            "id": self.id,
            "concept": self.concept,
            "detail": self.detail,
            "description": self.description,
            "is_active": self.is_active,
        }
