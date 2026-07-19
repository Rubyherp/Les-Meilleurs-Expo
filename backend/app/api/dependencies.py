from app.services.storage import Storage, get_storage
from app.services.tasks import CeleryTaskDispatcher, TaskDispatcher


def get_storage_service() -> Storage:
    return get_storage()


def get_task_dispatcher() -> TaskDispatcher:
    return CeleryTaskDispatcher()
