from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Video Analysis API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/video_analysis"
    redis_url: str = "redis://localhost:6379/0"
    storage_backend: str = "s3"
    local_storage_path: str = ".storage"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "video-analysis"
    s3_region: str = "us-east-1"
    max_upload_size_bytes: int = 524_288_000
    allowed_video_content_types: str = (
        "video/mp4,video/quicktime,video/webm,video/x-matroska"
    )
    sample_fps: float | None = Field(default=None, gt=0)
    frame_stride: int = Field(default=1, ge=1)
    detector_confidence: float = Field(default=0.25, ge=0, le=1)
    max_persons: int = Field(default=5, ge=1)
    crop_padding: float = Field(default=0.15, ge=0, le=1)
    tracker_name: str = "bytetrack.yaml"
    tracker_buffer_seconds: float = Field(default=2.0, ge=0)
    tracker_buffer_frames: int | None = Field(default=None, ge=0)
    tracker_iou_threshold: float = Field(default=0.1, ge=0, le=1)
    tracker_high_confidence: float = Field(default=0.25, ge=0, le=1)
    tracker_low_confidence: float = Field(default=0.1, ge=0, le=1)
    grid_columns: int = Field(default=10, ge=1)
    grid_rows: int = Field(default=10, ge=1)
    comparison_max_dancers: int = Field(default=24, ge=1, le=24)
    comparison_min_coverage: float = Field(default=0.5, ge=0, le=1)
    comparison_max_cost: float = Field(default=1.0, ge=0)
    comparison_unmatched_penalty: float = Field(default=1.25, ge=0)
    comparison_include_predicted: bool = False
    comparison_predicted_weight: float = Field(default=0.1, gt=0, le=1)
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3
    yolo_model_path: str = "models/yolo11n.pt"
    pose_model_path: str = "models/pose_landmarker_lite.task"
    ml_device: str = "cpu"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    @property
    def allowed_video_types(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.allowed_video_content_types.split(",")
            if item.strip()
        }

    @model_validator(mode="after")
    def validate_tracker_thresholds(self) -> "Settings":
        if self.tracker_high_confidence < self.tracker_low_confidence:
            raise ValueError("TRACKER_HIGH_CONFIDENCE must be at least TRACKER_LOW_CONFIDENCE")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
