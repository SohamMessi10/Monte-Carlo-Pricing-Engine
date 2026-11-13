"""The README's usage example must run as written."""

import re
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


def test_readme_python_example_runs(capsys):
    blocks = re.findall(r"```python\n(.*?)```", README.read_text(), flags=re.DOTALL)
    assert len(blocks) == 1
    exec(compile(blocks[0], str(README), "exec"), {})
    printed = capsys.readouterr().out.split()
    assert len(printed) == 5  # estimate, std_error, n_paths, elapsed, Black–Scholes
