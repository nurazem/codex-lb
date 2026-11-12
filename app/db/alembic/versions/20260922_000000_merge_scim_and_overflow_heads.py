"""Keep the fork's deployed SCIM/overflow merge revision addressable.

This fork deployed this no-op merge of ``20260914_000000_add_scim_tokens`` and
``20260914_000000_drop_subscription_overflow_schema`` before upstream published
its own equivalent, ``20260918_000000_merge_scim_and_overflow_heads``. Databases
already stamped with this id must stay on a known revision, so it now descends
from upstream's merge instead of repeating it, which keeps a single head.
"""

revision = "20260922_000000_merge_scim_and_overflow_heads"
down_revision = "20260918_000000_merge_scim_and_overflow_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
