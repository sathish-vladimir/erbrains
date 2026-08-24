from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthReadingCreate(BaseModel):
    client_reading_id: str = Field(..., description="Client-generated UUID, used to de-dupe on sync")
    device_id: int
    heart_rate: int | None = None
    spo2: int | None = None
    steps: int | None = None
    battery: int | None = None
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def _strip_tzinfo(cls, value: datetime) -> datetime:
        """The Flutter client sends ISO-8601 timestamps with a 'Z' suffix,
        which Pydantic parses as timezone-aware. The DB column is a plain
        (naive) DATETIME, and MySQL/pymysql errors out (500) if handed a
        tz-aware value. Normalize to naive UTC here so every write path
        (single + batch) is safe."""
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class HealthReadingBatchCreate(BaseModel):
    """Used by the offline sync queue to push many readings in one request."""
    readings: list[HealthReadingCreate]


class HealthReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_reading_id: str
    user_id: int
    device_id: int
    heart_rate: int | None = None
    spo2: int | None = None
    steps: int | None = None
    battery: int | None = None
    recorded_at: datetime
    created_at: datetime


class HealthReadingBatchResponse(BaseModel):
    created: list[HealthReadingResponse]
    duplicates_skipped: int


class HealthSummaryResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    avg_heart_rate: float | None = None
    avg_spo2: float | None = None
    total_steps: int
    reading_count: int