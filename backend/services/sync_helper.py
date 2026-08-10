import threading
import asyncio
import logging
from django.db import close_old_connections

logger = logging.getLogger(__name__)

def run_sync_in_thread(func, *args, **kwargs):
    """
    Executes a function requiring Playwright Sync API inside a dedicated OS thread
    with an isolated asyncio event loop context.
    
    This guarantees that sync_playwright().start() will not conflict with
    asyncio event loops created elsewhere (such as in async_playwright discovery tasks).
    """
    res = []
    err = []

    def target():
        # Set up a clean event loop for this background thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            val = func(*args, **kwargs)
            res.append(val)
        except Exception as e:
            logger.error(f"Error executing sync playwright target: {e}")
            err.append(e)
        finally:
            try:
                loop.close()
            except Exception:
                pass
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            close_old_connections()

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join()

    if err:
        raise err[0]
    return res[0] if res else None
