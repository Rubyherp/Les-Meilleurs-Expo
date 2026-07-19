import asyncio
import io
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

import boto3
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class StoredObject:
    object_key: str


class Storage(Protocol):
    async def upload(self, file_obj: BinaryIO, object_key: str, content_type: str) -> StoredObject: ...

    async def download(self, object_key: str) -> BinaryIO: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    async def upload(self, file_obj: BinaryIO, object_key: str, content_type: str) -> StoredObject:
        destination = self.root / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._copy, file_obj, destination)
        return StoredObject(object_key=object_key)

    async def download(self, object_key: str) -> BinaryIO:
        return await asyncio.to_thread(self._open, object_key)

    def _open(self, object_key: str) -> BinaryIO:
        destination = (self.root / object_key).resolve()
        root = self.root.resolve()
        if root not in destination.parents:
            raise ValueError("Storage object key escapes the local storage root.")
        return destination.open("rb")

    @staticmethod
    def _copy(file_obj: BinaryIO, destination: Path) -> None:
        with destination.open("wb") as output:
            shutil.copyfileobj(file_obj, output)


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )

    async def upload(self, file_obj: BinaryIO, object_key: str, content_type: str) -> StoredObject:
        await asyncio.to_thread(self._upload, file_obj, object_key, content_type)
        return StoredObject(object_key=object_key)

    async def download(self, object_key: str) -> BinaryIO:
        return await asyncio.to_thread(self._download, object_key)

    def _upload(self, file_obj: BinaryIO, object_key: str, content_type: str) -> None:
        try:
            self.client.head_bucket(Bucket=self.settings.s3_bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.settings.s3_bucket)
        self.client.upload_fileobj(
            file_obj,
            self.settings.s3_bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )

    def _download(self, object_key: str) -> BinaryIO:
        response = self.client.get_object(Bucket=self.settings.s3_bucket, Key=object_key)
        return io.BytesIO(response["Body"].read())


def get_storage(settings: Settings | None = None) -> Storage:
    settings = settings or get_settings()
    if settings.storage_backend.lower() == "local":
        return LocalStorage(settings.local_storage_path)
    return S3Storage(settings)
