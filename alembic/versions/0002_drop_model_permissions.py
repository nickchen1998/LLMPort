"""每個帳號都能用全部啟用中的模型：拿掉會員與金鑰的可用模型限制

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("api_key_model")
    op.drop_table("user_model")


def downgrade() -> None:
    op.create_table(
        "user_model",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("llm_model.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "api_key_model",
        sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_key.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("llm_model.id", ondelete="CASCADE"), primary_key=True),
    )
