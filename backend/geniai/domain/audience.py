"""Which conversations the bot serves. A conversation it does not serve goes to the team at once, with no
reply, no ticket and no LLM call (see app/handle_inbound.py).

The group rule is an assumption about how the WhatsApp connector shows a group in Chatwoot, not yet
checked against the real inbox: the chat id of a WhatsApp group ends in "@g.us", and a group has no
contact phone the bot can use. Changing the rule must only require changing this file.
"""

from typing import Literal

from geniai.domain.phone import normalize_br_phone

GROUP_SUFFIX = "@g.us"

NotServedReason = Literal["group", "no_phone", "not_in_test_list"]


def is_group(phone: str | None, contact_identifier: str | None) -> bool:
    return any(
        value is not None and value.strip().lower().endswith(GROUP_SUFFIX) for value in (phone, contact_identifier)
    )


def not_served_reason(
    phone: str | None, contact_identifier: str | None, only_phones: frozenset[str]
) -> NotServedReason | None:
    """None when the bot serves the conversation. `only_phones` is the test mode list (normalized, see
    config.py): empty serves every phone. A group, or a contact with no usable Brazilian phone, is never
    served."""
    if is_group(phone, contact_identifier):
        return "group"
    normalized = None if phone is None else normalize_br_phone(phone)
    if normalized is None:
        return "no_phone"
    if only_phones and normalized not in only_phones:
        return "not_in_test_list"
    return None
