"""
RecordFile model for AHML Fondos application.

Defines the database model for documentary files/expedientes.
Includes archival references (fund, section, series), physical location,
availability status, preservation dates and audit timestamps.
"""

from datetime import date
from app.extensions import db


class RecordFile(db.Model):
    """Represents a documentary record (expediente) in the archive.

    Attributes:
        id (int): Unique identifier of the record file.
        reference_code (str): Classification code built from fund/section/series and year/number.
        file_number (str): Internal or sequential number within the series.
        subject (str): Descriptive title or main topic of the record file.
        # typologies (list|json): Document typologies associated to the record (stored as JSON array of IDs).
        sensitive_data (bool): Indicates if the record contains sensitive/confidential information.
        user_id (int): Identifier of the user who created or updated the record.
        comments (str): Additional notes or observations about the record.
        availability_status (str): Current availability (available / unavailable / under_review / on_loan).

        fund_id (int): Identifier of the fund this record belongs to (fund.id).
        section_id (int): Identifier of the section this record belongs to (section.id).
        series_id (int): Identifier of the series this record belongs to (series.id).
        location_id (int): Identifier of the physical location where the record is stored.

        box_number (str): Physical box number where the record is archived.
        page_count (int): Total number of pages/folios in the record.

        file_date (date): Date of the main document or related event.
        created_at (datetime): Timestamp when the record was first created.
        updated_at (datetime): Timestamp when the record was last updated.
        deleted_at (datetime): Timestamp of logical deletion (if any).

        last_preservation_date (date): Date of the last preservation-related action.
        last_fund_date (date): Last date when the record was associated to the fund/period.
        deterioration_status_id (int): Current conservation/deterioration status.
        deterioration_status_updated_at (datetime): Timestamp of the last conservation status update.
    """

    __tablename__ = "record_file"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    reference_code = db.Column(db.String(255), nullable=False)
    file_number = db.Column(db.String(50), nullable=True)
    subject = db.Column(db.String(255), nullable=False)

    # typologies as JSON array of IDs
    # typologies = db.Column(db.JSON, nullable=True, default=list)

    sensitive_data = db.Column(db.Boolean, default=False, nullable=False)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    comments = db.Column(db.Text, nullable=True)

    availability_status = db.Column(
        db.String(20),
        nullable=False,
        default="available",
    )

    # archival references
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

    # physical data
    box_number = db.Column(db.String(50), nullable=True)
    page_count = db.Column(db.Integer, nullable=True)

    # documentary date
    file_date = db.Column(db.Date, nullable=True)

    # audit (usar hora del servidor MySQL)
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

    # preservation / conservation
    last_preservation_date = db.Column(db.Date, nullable=True)
    last_fund_date = db.Column(db.Date, nullable=True)

    deterioration_status_id = db.Column(
        db.Integer,
        db.ForeignKey("deterioration.id"),
        nullable=True,
    )
    deterioration_status_updated_at = db.Column(db.DateTime, nullable=True)

    # relations
    fund = db.relationship("Fund", backref="record_files", lazy=True)
    section = db.relationship("Section", backref="record_files", lazy=True)
    series = db.relationship("Series", backref="record_files", lazy=True)
    location = db.relationship("Location", backref="record_files", lazy=True)
    user = db.relationship("User", backref="record_files", lazy=True)
    deterioration_status = db.relationship("Deterioration", backref="record_files", lazy=True)

    def __repr__(self) -> str:
        return f"<RecordFile {self.id}: {self.reference_code} - {self.subject}>"

    def to_json(self) -> dict:
        """Serialize the record file to a JSON-friendly dict."""
        return {
            "id": self.id,
            "reference_code": self.reference_code,
            "file_number": self.file_number,
            "subject": self.subject,
            # "typologies": self.typologies,
            "sensitive_data": self.sensitive_data,
            "user_id": self.user_id,
            "comments": self.comments,
            "availability_status": self.availability_status,
            "fund_id": self.fund_id,
            "section_id": self.section_id,
            "series_id": self.series_id,
            "location_id": self.location_id,
            "box_number": self.box_number,
            "page_count": self.page_count,
            "file_date": self.file_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "last_preservation_date": self.last_preservation_date,
            "last_fund_date": self.last_fund_date,
            "deterioration_status_id": self.deterioration_status_id,
            "deterioration_status_updated_at": self.deterioration_status_updated_at,
        }
