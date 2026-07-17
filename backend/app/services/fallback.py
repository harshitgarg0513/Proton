from __future__ import annotations

from pathlib import Path
from shutil import copy2


def keep_original_if_larger(source_path: str, optimized_path: str) -> tuple[str, int, bool]:
    original_size = Path(source_path).stat().st_size
    optimized_size = Path(optimized_path).stat().st_size
    if optimized_size < original_size:
        return optimized_path, optimized_size, True

    Path(optimized_path).unlink(missing_ok=True)
    fallback_path = Path(optimized_path).parent / Path(source_path).name
    copy2(source_path, fallback_path)
    return str(fallback_path), original_size, False
