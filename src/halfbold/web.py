import re
from pathlib import Path

from halfbold.scan import Kind


def set_web_font(css_path: Path, kind: Kind, family: str) -> str:
    text = css_path.read_text()
    pattern = re.compile(rf'^(\s*--halfbold-{kind}:\s*)"[^"]*"(;)$', re.MULTILINE)
    new_text, count = pattern.subn(rf'\g<1>"{family}"\g<2>', text)
    if count != 1:
        raise ValueError(f"{css_path} has no --halfbold-{kind} line to replace")
    css_path.write_text(new_text)
    return f"{kind:<6} {family}"
