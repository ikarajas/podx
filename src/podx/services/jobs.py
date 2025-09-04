from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import tempfile
import uuid

from .progress import ProgressReporter
from .ingestion import IngestionService


@dataclass
class Job:
    id: str
    type: str  # 'transcribe' | 'summarize'
    podcast: str
    title: str
    feed_url: str
    guid: Optional[str] = None
    enclosure_url: Optional[str] = None
    published_date: Optional[str] = None
    status: str = "queued"  # queued | running | succeeded | failed | canceled
    percent: int = 0
    message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    # Result paths (if any)
    episode_dir: Optional[str] = None
    vtt_path: Optional[str] = None
    txt_path: Optional[str] = None


class _JobProgressReporter(ProgressReporter):
    def __init__(self, job_id: str, on_update: Callable[[str, int, int, int], None]) -> None:
        self.job_id = job_id
        self._cb = on_update

    def on_update(self, percent: int, current_sec: int, total_sec: int) -> None:  # pragma: no cover - simple bridge
        try:
            self._cb(self.job_id, percent, current_sec, total_sec)
        except Exception:
            pass


class JobsService:
    """Queue and run background jobs (transcribe, summarize) with progress.

    UI code can subscribe to updates via ``add_listener``; listeners are called
    on the worker thread, so UIs should marshal updates to the main thread.
    """

    def __init__(self, ingestion: IngestionService) -> None:
        self._ingestion = ingestion
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._jobs: Dict[str, Job] = {}
        self._listeners: List[Callable[[Job], None]] = []

    # Subscriptions
    def add_listener(self, cb: Callable[[Job], None]) -> None:
        self._listeners.append(cb)

    def _notify(self, job: Job) -> None:
        for cb in list(self._listeners):
            try:
                cb(job)
            except Exception:
                # Ignore listener errors to avoid stalling the queue
                pass

    # Introspection
    def list_jobs(self) -> List[Job]:
        return list(self._jobs.values())

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    # Enqueue operations
    def enqueue_transcription(
        self,
        *,
        podcast: str,
        title: str,
        feed_url: str,
        enclosure_url: str,
        guid: Optional[str] = None,
        published_date: Optional[str] = None,
        force: bool = False,
    ) -> str:
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id,
            type="transcribe",
            podcast=podcast,
            title=title,
            feed_url=feed_url,
            guid=guid,
            enclosure_url=enclosure_url,
            published_date=published_date,
        )
        self._jobs[job_id] = job
        self._notify(job)

        def run():
            job.status = "running"
            job.started_at = datetime.now().isoformat()
            self._notify(job)
            # Download the enclosure to a temporary file
            tmp_path: Optional[Path] = None
            try:
                from urllib.request import urlopen
                with urlopen(enclosure_url) as resp:
                    data = resp.read()
                fd, p = tempfile.mkstemp(suffix=".mp3")
                Path(p).write_bytes(data)
                tmp_path = Path(p)
            except Exception as e:
                job.status = "failed"
                job.message = f"Download failed: {e}"
                job.finished_at = datetime.now().isoformat()
                self._notify(job)
                return

            reporter = _JobProgressReporter(job_id, self._on_progress)
            try:
                # Ingest; this will emit progress via reporter
                result = self._ingestion.ingest_episode(
                    tmp_path,
                    podcast=podcast,
                    episode=title,
                    force=force,
                    reporter=reporter,
                    feed_url=feed_url,
                    enclosure_url=enclosure_url,
                    guid=guid,
                )
                job.percent = max(job.percent, 100)
                job.status = "succeeded"
                job.message = "Transcribed" if result is not None else "Up-to-date"
                if result is not None:
                    job.episode_dir = str(result.path)
                    job.vtt_path = str(result.transcript.vtt_path)
                    job.txt_path = str(result.transcript.txt_path)
            except Exception as e:
                job.status = "failed"
                job.message = str(e)
            finally:
                if tmp_path is not None:
                    try:
                        tmp_path.unlink(missing_ok=True)  # type: ignore[call-arg]
                    except Exception:
                        pass
                job.finished_at = datetime.now().isoformat()
                self._notify(job)

        self._executor.submit(run)
        return job_id

    # Progress callback from reporter
    def _on_progress(self, job_id: str, percent: int, _cur: int, _total: int) -> None:
        job = self._jobs.get(job_id)
        if not job or job.status not in {"queued", "running"}:
            return
        if percent > job.percent:
            job.percent = percent
            job.status = "running"
            self._notify(job)


__all__ = ["JobsService", "Job"]

