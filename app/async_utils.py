import asyncio
from functools import partial
from typing import Any, Callable


async def run_sync(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous blocking function in the default thread pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))
