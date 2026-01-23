"""
RecordFile model for AHML Fondos application.

Defines the database model for documentary files/expedientes.
Includes archival references (fund, section, series), physical location,
availability status, preservation dates and audit timestamps.
"""

from datetime import datetime, timezone
from app.extensions import db


class RecordFile(db.Model):
    """Represents a documentary record (expediente) in the archive.

    Attributes:
        id (int): Unique identifier of the record file.
        reference_code (str): Classification code built from fund/section/series and number.
        file_number (str): Internal or sequential number within the series/box.
        subject (str): Descriptive title or main topic of the record file.
        sensitive_data (bool): Indicates if the record contains sensitive/confidential information.
        user_id (int): Identifier of the user who created or updated the record.
        comments (str): Additional notes or observations about the record.
        availability_status (str): Current availability (available / unavailable / under_review / on_loan).
        fund_id (int): FK to fund.id.
        section_id (int): FK to section.id.
        series_id (int): FK to series.id.
        location_id (int): FK to location.id.
        box_id (int): FK to box.id.
        page_count (int): Total number of pages.
        file_date (date): Main document date.
        created_at (datetime): Creation timestamp.
        updated_at (datetime): Last update timestamp.
        deleted_at (datetime): Soft delete timestamp.
        last_preservation_date (date): Last preservation action date.
        last_fund_date (date): Last date associated to the fund/period.
        deterioration_status_id (int): FK to deterioration.id.
        deterioration_status_updated_at (datetime): When deterioration status was updated.
    """

    __tablename__ = "record_file"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # lo vamos a generar en el endpoint, pero aquí lo dejamos NOT NULL
    reference_code = db.Column(db.String(255), nullable=False)
    previous_reference_code = db.Column(db.String(255), nullable=True)
    # nuevo campo para construir el código
    file_number = db.Column(db.String(50), nullable=True)

    subject = db.Column(db.String(1500), nullable=False)

    # confidencialidad
    sensitive_data = db.Column(db.Boolean, default=False, nullable=False)

    # quién lo creó / actualizó
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    comments = db.Column(db.Text, nullable=True)

    # available / unavailable / under_review / on_loan
    availability_status = db.Column(
        db.String(20),
        nullable=False,
        default="available",
    )

    # referencias archivísticas
    fund_id = db.Column(
        db.Integer,
        db.ForeignKey("fund.id"),
        nullable=True,
    )
    section_id = db.Column(
        db.Integer,
        db.ForeignKey("section.id"),
        nullable=True,
    )
    series_id = db.Column(
        db.Integer,
        db.ForeignKey("series.id"),
        nullable=True,
    )
    location_id = db.Column(
        db.Integer,
        db.ForeignKey("location.id"),
        nullable=True,
    )

    # datos físicos
    box_id = db.Column(
    db.Integer,
    db.ForeignKey("box.id"),
    nullable=True,
)
    page_count = db.Column(db.Integer, nullable=True)
    document_sizes = db.Column(db.String(500), nullable=True)

    # fecha documental
    file_date = db.Column(db.Date, nullable=True)

    # auditoría
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

    # preservación / conservación
    last_preservation_date = db.Column(db.Date, nullable=True)
    last_fund_date = db.Column(db.Date, nullable=True)

    deterioration_status_id = db.Column(
        db.Integer,
        db.ForeignKey("deterioration.id"),
        nullable=True,
    )
    deterioration_status_updated_at = db.Column(db.DateTime, nullable=True)

    # relaciones
    fund = db.relationship("Fund", backref="record_files", lazy=True)
    section = db.relationship("Section", backref="record_files", lazy=True)
    series = db.relationship("Series", backref="record_files", lazy=True)
    location = db.relationship("Location", backref="record_files", lazy=True)
    user = db.relationship("User", backref="record_files", lazy=True)
    deterioration_status = db.relationship("Deterioration", backref="record_files", lazy=True)
    box = db.relationship("Box", backref="record_files", lazy=True)

    def __repr__(self) -> str:
        return f"<RecordFile {self.id}: {self.reference_code} - {self.subject}>"

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "reference_code": self.reference_code,
            "previous_reference_code": self.previous_reference_code,
            "file_number": self.file_number,
            "subject": self.subject,
            "sensitive_data": self.sensitive_data,
            "user_id": self.user_id,
            "comments": self.comments,
            "availability_status": self.availability_status,
            "fund_id": self.fund_id,
            "section_id": self.section_id,
            "series_id": self.series_id,
            "location_id": self.location_id,
            "box_id": self.box_id,
            "page_count": self.page_count,
            "document_sizes": self.document_sizes,
            "file_date": self.file_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "last_preservation_date": self.last_preservation_date,
            "last_fund_date": self.last_fund_date,
            "deterioration_status_id": self.deterioration_status_id,
            "deterioration_status_updated_at": self.deterioration_status_updated_at,
        }
        