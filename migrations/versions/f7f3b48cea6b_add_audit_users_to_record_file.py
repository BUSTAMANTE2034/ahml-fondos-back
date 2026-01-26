"""add audit users to record_file

Revision ID: f7f3b48cea6b
Revises: c71afd8c9120
Create Date: 2026-01-26 11:55:51.387189

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'f7f3b48cea6b'
down_revision = 'c71afd8c9120'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('diagnosis_catalog') as batch_op:
        batch_op.alter_column(
            'user_id',
            existing_type=mysql.INTEGER(display_width=11),
            nullable=True
        )

    with op.batch_alter_table('record_file') as batch_op:
        batch_op.add_column(
            sa.Column('updated_by_id', sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('deleted_by_id', sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_record_file_updated_by_user',
            'user',
            ['updated_by_id'],
            ['id']
        )
        batch_op.create_foreign_key(
            'fk_record_file_deleted_by_user',
            'user',
            ['deleted_by_id'],
            ['id']
        )

def downgrade():
    with op.batch_alter_table('record_file') as batch_op:
        batch_op.drop_constraint(
            'fk_record_file_updated_by_user',
            type_='foreignkey'
        )
        batch_op.drop_constraint(
            'fk_record_file_deleted_by_user',
            type_='foreignkey'
        )
        batch_op.drop_column('deleted_by_id')
        batch_op.drop_column('updated_by_id')

    with op.batch_alter_table('diagnosis_catalog') as batch_op:
        batch_op.alter_column(
            'user_id',
            existing_type=mysql.INTEGER(display_width=11),
            nullable=False
        )
