"""
Self-Healing Network Operation Retry Decorator with Exponential Backoff.
Adheres to Documents/Structure/01_ARCHITECTURE_CONSTRAINED_AI.md (Rule <= 150 lines/file).
Enforces >= 3 retries with exponential backoff for network and external API calls.
"""

import time
import functools
import logging
from typing import Callable, Any, Tuple, Type, Optional

logger = logging.getLogger("network_retry")


def retry_network_op(
    func: Optional[Callable] = None,
    *,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger_instance: Optional[logging.Logger] = None
) -> Callable:
    """
    Decorator that retries network operations with exponential backoff.
    Can be used as @retry_network_op or @retry_network_op(max_retries=3, initial_delay=1.0).
    Guarantees >=3 retries by default.
    """
    actual_retries = max(3, max_retries)

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            log = logger_instance or logger
            current_delay = initial_delay
            last_exception = None

            for attempt in range(1, actual_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as err:
                    last_exception = err
                    if attempt >= actual_retries:
                        log.error(
                            f"[RETRY] '{fn.__name__}' failed permanently after "
                            f"{attempt}/{actual_retries} attempts: {err}"
                        )
                        raise
                    log.warning(
                        f"[RETRY] '{fn.__name__}' failed (attempt {attempt}/{actual_retries}): "
                        f"{err}. Retrying in {current_delay:.2f}s..."
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff_factor

            if last_exception is not None:
                raise last_exception

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
