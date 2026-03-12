"""Graceful shutdown manager for the DataX application.

Tracks in-flight SSE connections and active queries so that on SIGTERM the
application can drain them before stopping. Exposes an asyncio Event that
signals shutdown has been requested and a ``wait_for_drain`` coroutine that
blocks until all tracked tasks finish or the drain timeout expires.
"""

from __future__ import annotations

import asyncio
import signal

from app.logging import get_logger

logger = get_logger(__name__)

# Default timeout for draining in-flight connections (seconds).
DRAIN_TIMEOUT_SECONDS: int = 30


class ShutdownManager:
    """Tracks in-flight work and orchestrates graceful drain on SIGTERM.

    Usage::

        mgr = ShutdownManager()
        mgr.install_signal_handlers()

        # In SSE / query handlers:
        token = mgr.track("sse")
        try:
            ...  # handle connection
        finally:
            mgr.untrack(token)

        # In lifespan shutdown:
        await mgr.wait_for_drain()
    """

    def __init__(self, drain_timeout: int = DRAIN_TIMEOUT_SECONDS) -> None:
        self.drain_timeout = drain_timeout
        self._shutdown_event = asyncio.Event()
        self._active: dict[int, str] = {}
        self._counter: int = 0
        self._lock = asyncio.Lock()

    @property
    def is_shutting_down(self) -> bool:
        """Return True once a shutdown signal has been received."""
        return self._shutdown_event.is_set()

    @property
    def active_count(self) -> int:
        """Number of currently tracked in-flight items."""
        return len(self._active)

    def install_signal_handlers(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Register SIGTERM (and SIGINT for dev) to trigger graceful shutdown.

        Must be called from the main thread *after* the event loop is running.
        In production, Kubernetes sends SIGTERM; locally, Ctrl-C sends SIGINT.
        """
        _loop = loop or asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            _loop.add_signal_handler(sig, self._handle_signal, sig)
        logger.info("shutdown_signals_installed", signals=["SIGTERM", "SIGINT"])

    def _handle_signal(self, sig: signal.Signals | int) -> None:
        sig_name = signal.Signals(sig).name if isinstance(sig, int) else sig.name
        logger.info("shutdown_signal_received", signal=sig_name)
        self._shutdown_event.set()
        # Raise SystemExit so uvicorn's shutdown logic kicks in and the
        # lifespan context manager can run its cleanup (drain, close pools).
        raise SystemExit(0)

    async def track(self, kind: str = "unknown") -> int:
        """Register an in-flight task (SSE connection, active query, etc.).

        Returns:
            An integer token used to untrack the task when it completes.
        """
        async with self._lock:
            self._counter += 1
            token = self._counter
            self._active[token] = kind
        return token

    async def untrack(self, token: int) -> None:
        """Mark a previously tracked task as finished."""
        async with self._lock:
            self._active.pop(token, None)

    async def wait_for_drain(self) -> None:
        """Block until all tracked tasks finish or the drain timeout expires.

        Intended to be called during lifespan shutdown, *after* the server has
        stopped accepting new connections.
        """
        if not self._active:
            logger.info("shutdown_drain_complete", remaining=0, reason="no_active_tasks")
            return

        logger.info(
            "shutdown_draining",
            active_count=len(self._active),
            timeout=self.drain_timeout,
            kinds=list(self._active.values()),
        )

        deadline = asyncio.get_event_loop().time() + self.drain_timeout
        while self._active and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.25)

        remaining = len(self._active)
        if remaining:
            logger.warning(
                "shutdown_drain_timeout",
                remaining=remaining,
                timeout=self.drain_timeout,
                kinds=list(self._active.values()),
            )
        else:
            logger.info("shutdown_drain_complete", remaining=0, reason="all_tasks_finished")
