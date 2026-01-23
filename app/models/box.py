from app.extensions import db


class Box(db.Model):
    """
    Represents a physical box that stores multiple record files.
    """

    __tablename__ = "box"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    box_number = db.Column(
        db.String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    physical_location_id = db.Column(
        db.Integer,
        db.ForeignKey("physical_location.id"),  # se actualiza para que apunte al modelo Location
        nullable=False,
    )

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
    physical_location = db.relationship(
    "PhysicalLocation",
    backref="boxes",
    lazy=True,
)
    user = db.relationship("User", backref="boxes", lazy=True)

    def __repr__(self) -> str:
        return f"<Box {self.box_number}>"

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "box_number": self.box_number,
            "physical_location_id": self.physical_location_id,
            "physical_location_name": (
                self.physical_location.name if self.physical_location else None
            ),
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "user_id": self.user_id,
        }
