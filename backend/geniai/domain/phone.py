import re

_NON_DIGIT = re.compile(r"[^0-9]")


def normalize_br_phone(raw: str) -> str | None:
    """Normalizes a Brazilian phone number to E.164 (+55 + 2-digit area code + subscriber).
    Mobiles stored with 8 digits (subscriber starting with 6-9) get the 9th digit.
    Anything that is not a Brazilian number returns None, and the caller treats the sender as
    unidentified. That includes internal WhatsApp ids (LID) that some connectors deliver instead of
    a phone.
    """
    trimmed = raw.strip()
    digits = _NON_DIGIT.sub("", trimmed)
    if trimmed.startswith("+"):
        if not digits.startswith("55"):
            return None
        national = digits[2:]
    elif len(digits) in (12, 13) and digits.startswith("55"):
        national = digits[2:]
    else:
        national = digits
    if len(national) not in (10, 11):
        return None
    area_code = national[:2]
    subscriber = national[2:]
    if area_code.startswith("0"):
        return None
    if len(subscriber) == 8 and subscriber[0] in "6789":
        subscriber = f"9{subscriber}"
    if len(subscriber) == 9 and not subscriber.startswith("9"):
        return None
    return f"+55{area_code}{subscriber}"
