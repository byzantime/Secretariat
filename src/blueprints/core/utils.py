from functools import wraps
from inspect import iscoroutinefunction

from quart import render_template


def async_partial(func, *args, **kwargs):
    """Create a partial function that works with both async and regular functions.

    Args:
        func: The function to partially apply
        *args: Positional arguments to fix
        **kwargs: Keyword arguments to fix

    Returns:
        A wrapper function that handles both async and regular functions
    """
    if iscoroutinefunction(func):

        @wraps(func)
        async def wrapper(*more_args, **more_kwargs):
            combined_kwargs = {**kwargs, **more_kwargs}
            return await func(*args, *more_args, **combined_kwargs)

    else:

        @wraps(func)
        def wrapper(*more_args, **more_kwargs):
            combined_kwargs = {**kwargs, **more_kwargs}
            return func(*args, *more_args, **combined_kwargs)

    return wrapper


async def get_macro(macro_name: str, *args, **kwargs) -> object:
    """Get a macro from a template file."""
    return await render_template(
        "render_macro.html",
        macro=macro_name,
        args=args,
        kwargs=kwargs,
    )
