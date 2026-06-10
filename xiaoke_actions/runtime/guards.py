from __future__ import annotations

import logging
from collections.abc import Callable


logger = logging.getLogger("xiaoke-actions.runtime")


def safely_record(callback: Callable[[], None]) -> None:
    """Keep status bookkeeping failures from affecting the action itself."""
    try:
        callback()
    except Exception:
        logger.exception("runtime_status_record_failed")
