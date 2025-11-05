"""
Loan model for AHML Fondos application.

Represents a loan (checkout) of a record file (expediente) to a user/area.
Stores who issued it, who has it, when it was loaned and when it was returned.
"""

from datetime import datetime, timezone
from app.extensions import db


class Loan(db.Model):
    """Represents a loan/checkout of an archival record file.

    Attributes:
        id (int): Unique identifier of the loan record.
        record_file_id (int): Identifier of the record file being loaned (record_file.id).
        issued_by_user_id (int): Identifier of the user who authorized/registered the loan.
        loaded_by_user_id (int): Identifier of the user who received/holds the loaned record.
        description (str): Description or reason for the loan.
        loaded_at (datetime): Datetime when the loan was made (when the record left the archive).
        returned_at (datetime): Datetime when the record was returned (if already returned).
        created_at (datetime): Datetime when the loan was registered in the system.
        updated_at (datetime): Datetime when the loan record was last updated.
        deleted_at (datetime): Logical deletion datetime (if the loan record was soft-deleted).
    """

    __tablename__ = "loan"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    record_file_id = db.Column(
        db.Integer,
        db.ForeignKey("record_file.id"),
        nullable=False,
    )

    # quién autorizó / registró el préstamo
    issued_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    # quién tiene físicamente el expediente
    loaded_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    description = db.Column(db.Text, nullable=True)

    # cuándo salió
    loaded_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # cuándo regresó (null mientras esté prestado)
    returned_at = db.Column(db.DateTime(timezone=True), nullable=True)

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

    # relaciones
    record_file = db.relationship("RecordFile", backref="loans", lazy=True)
    issued_by_user = db.relationship("User", foreign_keys=[issued_by_user_id], backref="issued_loans", lazy=True)
    loaded_by_user = db.relationship("User", foreign_keys=[loaded_by_user_id], backref="received_loans", lazy=True)

    def __repr__(self):
        return f"<Loan {self.id}: record_file={self.record_file_id}>"

    def to_json(self):
        """Serialize the loan to a JSON-friendly dict."""
        return {
            "id": self.id,
            "record_file_id": self.record_file_id,
            "issued_by_user_id": self.issued_by_user_id,
            "loaded_by_user_id": self.loaded_by_user_id,
            "description": self.description,
            "loaded_at": self.loaded_at,
            "returned_at": self.returned_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
