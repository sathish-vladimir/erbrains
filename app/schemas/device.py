from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeviceCreate(BaseModel):
    device_id: str
    name: str | None = None
    battery: int | None = None
    connection_status: str = "connected"


class DeviceUpdate(BaseModel):
    name: str | None = None
    battery: int | None = None
    connection_status: str | None = None


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    user_id: int
    name: str | None = None
    battery: int | None = None
    connection_status: str
    created_at: datetime
