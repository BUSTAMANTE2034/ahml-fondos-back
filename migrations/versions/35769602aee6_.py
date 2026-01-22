"""add foreign key diagnosis_catalog.user_id -> user.id

Revision ID: 35769602aee6
Revises: d7f52565f22b
Create Date: 2026-01-19 13:50:08.118123
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '35769602aee6'
down_revision = 'd7f52565f22b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('diagnosis_catalog') as batch_op:
        batch_op.create_foreign_key(
            'fk_diagnosis_catalog_user',
            'user',
            ['user_id'],
            ['id'],
            ondelete='RESTRICT'
        )


def downgrade():
    with op.batch_alter_table('diagnosis_catalog') as batch_op:
        batch_op.drop_constraint(
            'fk_diagnosis_catalog_user',
            type_='foreignkey'
        )
