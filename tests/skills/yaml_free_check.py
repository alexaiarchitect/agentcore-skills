"""A minimal structural check for generated YAML, without a YAML dependency.

It catches the mistakes a template can make (tabs, odd indentation, an
unclosed `${{`), not every YAML error.
"""


def assert_balanced_yaml(text: str) -> None:
    for number, line in enumerate(text.splitlines(), start=1):
        assert "\t" not in line, f"line {number}: tab"
        indent = len(line) - len(line.lstrip(" "))
        assert indent % 2 == 0, f"line {number}: odd indentation"
        assert line.count("${{") == line.count("}}"), f"line {number}: unbalanced expression"
