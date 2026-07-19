from typing import Protocol
from uuid import UUID

from app.tasks.analysis import run_analysis


class TaskDispatcher(Protocol):
    def enqueue(self, job_id: UUID) -> str: ...


class CeleryTaskDispatcher:
    def enqueue(self, job_id: UUID) -> str:
        result = run_analysis.apply_async(args=[str(job_id)], task_id=str(job_id))  # type: ignore[attr-defined]
        return result.id
