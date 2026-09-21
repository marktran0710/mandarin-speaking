"""Load bounded source parts into one module namespace.

This is intentionally small: the facade remains the import-compatible public
module while the parts execute in order and share globals exactly as the
pre-refactor module did.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_module_parts(namespace: dict[str, Any], module_file: str) -> None:
    module_path = Path(module_file)
    parts_dir = module_path.with_name(f"{module_path.stem}_parts")
    for part_path in sorted(parts_dir.glob("part_*.py")):
        code = compile(
            part_path.read_text(encoding="utf-8"),
            str(part_path),
            "exec",
        )
        exec(code, namespace, namespace)
