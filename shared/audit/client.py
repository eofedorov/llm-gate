"""AuditClient: async queue + batch HTTP to audit-service."""

import asyncio
import logging
from typing import Any

from audit.context import get_span_id, get_trace_id
from audit.schemas import AuditEvent

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50
DEFAULT_FLUSH_INTERVAL_SEC = 1.0
DEFAULT_MAX_QUEUE_SIZE = 1000
DEFAULT_TIMEOUT_SEC = 0.5
DEFAULT_FLUSH_MAX_RETRIES = 3
DEFAULT_FLUSH_RETRY_DELAY_SEC = 0.15


class AuditClient:
    """
    Sends audit events via async queue; background worker batches (50 items / 1 sec)
    and POSTs to /v1/events/batch. Drops events when queue exceeds max size.
    """

    def __init__(
        self,
        base_url: str,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval_sec: float = DEFAULT_FLUSH_INTERVAL_SEC,
        max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        service: str = "unknown",
        env: str = "dev",
        sync_mode: bool = False,
        flush_max_retries: int = DEFAULT_FLUSH_MAX_RETRIES,
        flush_retry_delay_sec: float = DEFAULT_FLUSH_RETRY_DELAY_SEC,
    ):
        self._base_url = base_url.rstrip("/")
        self._batch_size = batch_size
        self._flush_interval = flush_interval_sec
        self._max_queue_size = max_queue_size
        self._timeout = timeout_sec
        self._service = service
        self._env = env
        self._sync_mode = sync_mode
        self._flush_max_retries = max(1, flush_max_retries)
        self._flush_retry_delay_sec = flush_retry_delay_sec
        self._queue: asyncio.Queue[AuditEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: asyncio.Task[None] | None = None
        self._started = False
        self._worker_loop: asyncio.AbstractEventLoop | None = None

    def _event(
        self,
        event_type: str,
        *,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        severity: str = "info",
        **attrs: Any,
    ) -> AuditEvent:
        from datetime import datetime

        return AuditEvent(
            ts=datetime.utcnow(),
            trace_id=get_trace_id(),
            service=self._service,
            env=self._env,
            event_type=event_type,
            span_id=span_id or get_span_id(),
            parent_span_id=parent_span_id,
            severity=severity,
            attrs=attrs,
        )

    async def emit(self, event: AuditEvent) -> None:
        """Enqueue one event. Drops if queue full (no block)."""
        if self._queue.qsize() >= self._max_queue_size:
            logger.warning(
                "audit queue full (max=%s), dropping event type=%s",
                self._max_queue_size,
                event.event_type,
            )
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "audit queue full, dropping event type=%s", event.event_type
            )

    def schedule_emit(self, event: AuditEvent) -> None:
        """
        Enqueue from sync code or another thread: runs put_nowait on the worker loop.
        Safe when AuditClient.start() was called on that loop (e.g. FastAPI lifespan).
        """
        if not self._started or self._worker_loop is None:
            logger.warning(
                "audit client not started, dropping event type=%s", event.event_type
            )
            return

        def _try_put() -> None:
            if self._queue.qsize() >= self._max_queue_size:
                logger.warning(
                    "audit queue full (max=%s), dropping event type=%s",
                    self._max_queue_size,
                    event.event_type,
                )
                return
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "audit queue full, dropping event type=%s", event.event_type
                )

        wl = self._worker_loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        if running is wl:
            _try_put()
        elif wl.is_running():
            wl.call_soon_threadsafe(_try_put)
        else:
            logger.warning(
                "audit worker loop not running, dropping event type=%s",
                event.event_type,
            )

    async def event(
        self,
        event_type: str,
        *,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        severity: str = "info",
        **attrs: Any,
    ) -> None:
        """Create and enqueue one event from current context."""
        ev = self._event(
            event_type,
            span_id=span_id,
            parent_span_id=parent_span_id,
            severity=severity,
            **attrs,
        )
        await self.emit(ev)

    async def _flush_batch(self, batch: list[AuditEvent]) -> bool:
        """POST batch to audit-service. Returns True if accepted (2xx)."""
        if not batch:
            return True
        import httpx

        url = f"{self._base_url}/v1/events/batch"
        payload = {"events": [e.model_dump(mode="json") for e in batch]}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(url, json=payload)
                if r.status_code >= 400:
                    logger.warning(
                        "audit-service POST %s status=%s body=%s",
                        url,
                        r.status_code,
                        r.text[:200],
                    )
                    return False
                return True
        except Exception as e:
            logger.warning("audit-service POST failed: %s", e)
            return False

    async def _worker(self) -> None:
        batch: list[AuditEvent] = []
        last_flush = asyncio.get_event_loop().time()

        while True:
            try:
                timeout = self._flush_interval - (asyncio.get_event_loop().time() - last_flush)
                timeout = max(0.01, min(timeout, self._flush_interval))
                try:
                    ev = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                    batch.append(ev)
                except asyncio.TimeoutError:
                    pass

                now = asyncio.get_event_loop().time()
                if len(batch) >= self._batch_size or (now - last_flush) >= self._flush_interval:
                    if batch:
                        for attempt in range(self._flush_max_retries):
                            ok = await self._flush_batch(batch)
                            if ok:
                                batch = []
                                break
                            if attempt + 1 < self._flush_max_retries:
                                await asyncio.sleep(
                                    self._flush_retry_delay_sec * (attempt + 1)
                                )
                        else:
                            logger.error(
                                "audit batch dropped after %s failed flush attempts (%s events)",
                                self._flush_max_retries,
                                len(batch),
                            )
                            batch = []
                    last_flush = now
            except asyncio.CancelledError:
                if batch:
                    for attempt in range(self._flush_max_retries):
                        ok = await self._flush_batch(batch)
                        if ok:
                            break
                        if attempt + 1 < self._flush_max_retries:
                            await asyncio.sleep(
                                self._flush_retry_delay_sec * (attempt + 1)
                            )
                raise
            except Exception as e:
                logger.exception("audit worker error: %s", e)

    async def start(self) -> None:
        """Start background worker. Idempotent."""
        if self._started:
            return
        self._started = True
        self._worker_loop = asyncio.get_running_loop()
        self._worker_task = asyncio.create_task(self._worker())
        logger.debug("audit client worker started")

    async def stop(self) -> None:
        """Stop worker and flush remaining events."""
        self._started = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        self._worker_loop = None

    def event_sync(
        self,
        event_type: str,
        *,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        severity: str = "info",
        **attrs: Any,
    ) -> None:
        """Sync variant: schedule emit in running event loop (for sync callers)."""
        if self._sync_mode:
            return
        ev = self._event(
            event_type,
            span_id=span_id,
            parent_span_id=parent_span_id,
            severity=severity,
            **attrs,
        )
        self.schedule_emit(ev)
