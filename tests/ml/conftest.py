"""Test configuration for ML tests.

The repository has no packaging configuration for the ``backend`` package yet
(``pyproject.toml`` is backend-owned), so the project root is added to
``sys.path`` explicitly instead of relying on an installed distribution.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
THIS_DIR = Path(__file__).resolve().parent
for candidate in (PROJECT_ROOT, THIS_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
