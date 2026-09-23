"""Mirror of geniai/db/migrations/*.sql. The SQL files are the source of truth for DDL."""

import sqlalchemy as sa

from geniai.domain.types import COLUMNS, HANDOFF_REASONS

metadata = sa.MetaData()

ticket_column_enum = sa.Enum(*COLUMNS, name="ticket_column", create_type=False)
handoff_reason_enum = sa.Enum(*HANDOFF_REASONS, name="handoff_reason", create_type=False)
move_actor_enum = sa.Enum("bot", "human", name="move_actor", create_type=False)
message_author_enum = sa.Enum("customer", "bot", name="message_author", create_type=False)


def _tz() -> sa.DateTime:
    return sa.DateTime(timezone=True)


schema_migration = sa.Table(
    "schema_migration",
    metadata,
    sa.Column("name", sa.Text, primary_key=True),
    sa.Column("applied_at", _tz(), nullable=False, server_default=sa.func.now()),
)

unit = sa.Table(
    "unit",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
)

attendant = sa.Table(
    "attendant",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("phone_e164", sa.Text, nullable=False, unique=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("unit_id", sa.Integer, sa.ForeignKey("unit.id"), nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
)

category = sa.Table(
    "category",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("key", sa.Text, unique=True),
    sa.Column("system", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("created_at", _tz(), nullable=False, server_default=sa.func.now()),
)

faq_item = sa.Table(
    "faq_item",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("category_id", sa.Integer, sa.ForeignKey("category.id"), nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("applies_when", sa.Text, nullable=False),
    sa.Column("answer_text", sa.Text, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
)

team_member = sa.Table(
    "team_member",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
)

ticket = sa.Table(
    "ticket",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("attendant_id", sa.Integer, sa.ForeignKey("attendant.id")),
    sa.Column("unit_id", sa.Integer, sa.ForeignKey("unit.id")),
    sa.Column("phone_e164", sa.Text),
    sa.Column("column", ticket_column_enum, nullable=False),
    sa.Column("category_id", sa.Integer, sa.ForeignKey("category.id")),
    sa.Column("bot_category_id", sa.Integer, sa.ForeignKey("category.id")),
    sa.Column("handoff_reason", handoff_reason_enum),
    sa.Column("faq_item_id", sa.Integer, sa.ForeignKey("faq_item.id")),
    sa.Column("faq_attempted", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("clarifications_asked", sa.Integer, nullable=False, server_default="0"),
    sa.Column("unclear_feedback_reasks", sa.Integer, nullable=False, server_default="0"),
    sa.Column("media_prompts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("summary", sa.Text, nullable=False, server_default=""),
    sa.Column("responsible_id", sa.Integer, sa.ForeignKey("team_member.id")),
    sa.Column("chatwoot_conversation_id", sa.Integer, nullable=False),
    sa.Column("opened_at", _tz(), nullable=False, server_default=sa.func.now()),
    sa.Column("handed_off_at", _tz()),
    sa.Column("taken_at", _tz()),
    sa.Column("closed_at", _tz()),
    sa.Column("last_customer_message_at", _tz(), nullable=False, server_default=sa.func.now()),
    sa.Column("last_moved_at", _tz(), nullable=False, server_default=sa.func.now()),
    sa.Column("last_consumed_message_id", sa.Integer),
)

ticket_move = sa.Table(
    "ticket_move",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("ticket_id", sa.Integer, sa.ForeignKey("ticket.id"), nullable=False),
    sa.Column("from_column", ticket_column_enum),
    sa.Column("to_column", ticket_column_enum, nullable=False),
    sa.Column("at", _tz(), nullable=False, server_default=sa.func.now()),
    sa.Column("actor", move_actor_enum, nullable=False),
)

triage_message = sa.Table(
    "triage_message",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("ticket_id", sa.Integer, sa.ForeignKey("ticket.id"), nullable=False),
    sa.Column("author", message_author_enum, nullable=False),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("is_media", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("at", _tz(), nullable=False, server_default=sa.func.now()),
    sa.Column("chatwoot_message_id", sa.Integer, unique=True),
)
