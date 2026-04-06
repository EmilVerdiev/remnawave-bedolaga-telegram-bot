"""Add unlimited traffic top-up (0 GB) at 4499 RUB to all tariffs.

Revision ID: 0055
Revises: 0054
Create Date: 2026-04-05

Merges key "0" -> 449900 kopeks into traffic_topup_packages.
Enables traffic_topup_enabled for tariffs with a finite base traffic limit (traffic_limit_gb > 0).
"""

from typing import Sequence, Union

from alembic import op

revision: str = '0055'
down_revision: Union[str, None] = '0054'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 4499 ₽ = 449900 kоп.
_UNLIMITED_KOPEKS = 449900


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE tariffs
        SET traffic_topup_packages = (
            COALESCE(traffic_topup_packages::jsonb, '{{}}'::jsonb)
            || jsonb_build_object('0', {_UNLIMITED_KOPEKS})
        )
        """
    )
    op.execute(
        """
        UPDATE tariffs
        SET traffic_topup_enabled = true
        WHERE traffic_limit_gb > 0
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE tariffs
        SET traffic_topup_packages = COALESCE(traffic_topup_packages::jsonb, '{}'::jsonb) - '0'
        """
    )
