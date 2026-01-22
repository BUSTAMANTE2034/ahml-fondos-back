from app.extensions import db

record_diagnosis_catalog = db.Table(
    "record_diagnosis_catalog",
    db.Column(
        "record_diagnosis_id",
        db.Integer,
        db.ForeignKey("record_diagnosis.id"),
        primary_key=True,
    ),
    db.Column(
        "diagnosis_catalog_id",
        db.Integer,
        db.ForeignKey("diagnosis_catalog.id"),
        primary_key=True,
    ),
)
