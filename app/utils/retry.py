from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, Optional, TypeVar

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


async def async_retry(
    func: Callable[..., Any],
    *args: Any,
    max_retries: Optional[int] = None,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
    **kwargs: Any,
) -> Any:
    """Retry an async callable with exponential back-off."""
    retries = max_retries if max_retries is not None else settings.MAX_RETRIES
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as exc:
            last_exc = exc
            if attempt == retries:
                break
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "Retrying after failure",
                attempt=attempt + 1,
                max_retries=retries,
                delay=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]


def sync_retry(
    func: Callable[..., T],
    *args: Any,
    max_retries: Optional[int] = None,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
    **kwargs: Any,
) -> T:
    """Retry a sync callable with exponential back-off."""
    retries = max_retries if max_retries is not None else settings.MAX_RETRIES
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as exc:
            last_exc = exc
            if attempt == retries:
                break
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "Retrying sync call",
                attempt=attempt + 1,
                max_retries=retries,
                delay=delay,
                error=str(exc),
            )
            time.sleep(delay)

    raise last_exc  # type: ignore[misc]


def with_async_retry(
    max_retries: Optional[int] = None,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator: retry an async function."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await async_retry(
                func,
                *args,
                max_retries=max_retries,
                base_delay=base_delay,
                exceptions=exceptions,
                **kwargs,
            )
        return wrapper
    return decorator
