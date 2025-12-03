"""
MovementHistory model for AHML Fondos application.

Stores the historical movements of a record file (expediente) between archive states
(e.g. archive, review, preservation, restoration), including who did it and when.
"""

from app.extensions import db


class MovementHistory(db.Model):
    """Represents a historical movement of a record file.

    Attributes:
        id (int): Unique identifier of the movement record.
        record_file_id (int): Identifier of the record file associated to the movement.
        moved_by_user_id (int): Identifier of the user who performed the movement.
        description (str): Description or reason for the movement.
        origin_status (str): Previous status of the record file (archive/review/preservation/restoration).
        destination_status (str): New status after the movement (archive/review/preservation/restoration).
        moved_at (datetime): Datetime when the movement was performed.
        created_at (datetime): Datetime when the movement record was created.
        updated_at (datetime): Datetime when the movement record was last updated.
        deleted_at (datetime): Logical deletion datetime (if the record was soft-deleted).
    """

    __tablename__ = "movement_history"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    record_file_id = db.Column(
        db.Integer,
        db.ForeignKey("record_file.id"),
        nullable=False,
    )

    moved_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )

    description = db.Column(db.Text, nullable=True)

    # e.g. archive / review / preservation / restoration
    origin_status = db.Column(db.String(50), nullable=True)
    destination_status = db.Column(db.String(50), nullable=True)

    # when the movement actually happened
    moved_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
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
    record_file = db.relationship("RecordFile", backref="movement_history", lazy=True)
    moved_by_user = db.relationship("User", backref="performed_movements", lazy=True)

    def __repr__(self):
        return (
            f"<MovementHistory {self.id}: rf={self.record_file_id} "
            f"{self.origin_status} -> {self.destination_status}>"
        )

    def to_json(self):
        """Serialize the movement history to a JSON-friendly dict."""
        return {
            "id": self.id,
            "record_file_id": self.record_file_id,
            "moved_by_user_id": self.moved_by_user_id,
            "description": self.description,
            "origin_status": self.origin_status,
            "destination_status": self.destination_status,
            "moved_at": self.moved_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
