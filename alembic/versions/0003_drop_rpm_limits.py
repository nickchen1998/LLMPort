"""不限制每分鐘請求數：拿掉帳號與金鑰的 rpm_limit

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("api_key", "rpm_limit")
    op.drop_column("user", "rpm_limit")
    op.execute("DELETE FROM system_setting WHERE key = 'default_rpm'")


def downgrade() -> None:
    op.add_column("user", sa.Column("rpm_limit", sa.Integer(), nullable=False, server_default="60"))
    op.add_column("api_key", sa.Column("rpm_limit", sa.Integer(), nullable=True))
