"""
Schemas de préstamos (Loan) para AHML Fondos.

Validan creación, actualización y salida de los registros de préstamo
de expedientes documentales.
"""

from marshmallow import Schema, fields, validate


class LoanBaseSchema(Schema):
    """Esquema base de un préstamo."""

    id = fields.Int(dump_only=True)

    record_file_id = fields.Int(
        required=True,
        error_messages={
            "required": "El ID del expediente es obligatorio.",
        },
    )


    description = fields.Str(required=False)

    loaded_at = fields.DateTime(dump_only=True)
    returned_at = fields.DateTime(dump_only=True)

    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    deleted_at = fields.DateTime(dump_only=True)


class LoanCreateSchema(LoanBaseSchema):
    """Esquema para crear un préstamo."""

    # si algún día quieres permitir que el front mande la fecha de salida, puedes
    # cambiar a load_only=True, required=False
    pass


class LoanUpdateSchema(Schema):
    """Esquema para actualizar un préstamo (ej. marcar devolución)."""

    id = fields.Int(
        required=True,
        error_messages={"required": "El ID del préstamo es obligatorio."},
    )
    description = fields.Str()
    returned_at = fields.DateTime()  # aquí sí permitimos que lo manden para marcar devuelto
    deleted_at = fields.DateTime()
    updated_at = fields.DateTime(dump_only=True)


class LoanResponseSchema(LoanBaseSchema):
    """Esquema de salida de préstamos."""
    pass
