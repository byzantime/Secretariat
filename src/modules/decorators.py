import inspect
import time
from functools import wraps

from quart import current_app
from quart import g


def _format_execution_time(func_name, execution_time, is_error=False, error=None):
    """Format execution time with appropriate units and precision."""
    if execution_time < 1.0:
        time_str = f"{execution_time * 1000:.2f}ms"
    else:
        time_str = f"{execution_time:.2f} seconds"

    if is_error:
        return f"{func_name} failed after {time_str} with error: {str(error)}"
    return f"{func_name} completed in {time_str}"


def perf_time(func=None, *, log_function=print):
    """Measure execution time of sync or async functions."""

    def decorator(func):
        # Check if the function is a coroutine function
        is_async = inspect.iscoroutinefunction(func)

        if is_async:

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    execution_time = time.perf_counter() - start_time
                    log_function(_format_execution_time(func.__name__, execution_time))
                    return result
                except Exception as e:
                    execution_time = time.perf_counter() - start_time
                    log_function(
                        _format_execution_time(func.__name__, execution_time, True, e)
                    )
                    raise

            return async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    execution_time = time.perf_counter() - start_time
                    log_function(_format_execution_time(func.__name__, execution_time))
                    return result
                except Exception as e:
                    execution_time = time.perf_counter() - start_time
                    log_function(
                        _format_execution_time(func.__name__, execution_time, True, e)
                    )
                    raise

            return sync_wrapper

    # If used without parentheses
    if func is not None:
        return decorator(func)

    # If used with parentheses
    return decorator
