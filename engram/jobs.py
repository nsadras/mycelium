"""Cancellation boundaries for native work and durable source admission."""

import asyncio


async def finish_before_cancelling(awaitable):
    """Wait for owned work to release resources before propagating cancellation.

    Cancelling asyncio.to_thread does not stop its native thread. Shielding that
    work keeps a device lock or upload cleanup from racing the running worker.
    Source admission uses the same boundary to finish its durable bookkeeping.
    """
    worker = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not worker.cancelled():
            worker.exception()
        raise
