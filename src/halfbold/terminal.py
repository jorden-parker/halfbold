import re

CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def escape_control_characters(text: str) -> str:
    return CONTROL_CHARACTERS.sub(lambda match: f"\\x{ord(match.group()):02x}", text)
