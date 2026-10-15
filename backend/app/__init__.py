"""Ghost-Rider application package.

Contains the typed configuration layer (:mod:`app.config`) and the deep system
diagnostics router (:mod:`app.health`).  The heavy compute modules (``pipeline``,
``s3_service``, ``bedrock_service``, ``database``) stay at the ``backend/`` level
so they remain importable as flat modules by uvicorn.
"""

from __future__ import annotations

__version__ = "2.1.0"
__all__ = ["__version__"]
