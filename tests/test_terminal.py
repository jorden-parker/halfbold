import pytest

from halfbold.terminal import escape_control_characters


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("\x1b]0;title\x07", "\\x1b]0;title\\x07"),
        ("\r\n\t\x08", "\\x0d\\x0a\\x09\\x08"),
        ("\x7f\x80\x9b\x9f", "\\x7f\\x80\\x9b\\x9f"),
        (
            "Café 黒体 😀 \\   ÿ  ",
            "Café 黒体 😀 \\   ÿ  ",
        ),
    ],
)
def test_escape_control_characters(text: str, escaped: str):
    assert escape_control_characters(text) == escaped
