from app.extensions import db


class PhysicalLocation(db.Model):
    """
    Represents a physical storage location (shelf, rack, aisle).
    Example: AAB2, RACK-01-N3
    """

    __tablename__ = "physical_location"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    code = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)

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

    # usuario y estado activo
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    is_active = db.Column(db.Boolean, default=True, nullable=True)

    # relaciones
    user = db.relationship("User", backref="physical_locations", lazy=True)

    def __repr__(self) -> str:
        return f"<PhysicalLocation {self.code}>"

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "user_id": self.user_id,
        }
