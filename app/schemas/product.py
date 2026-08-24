from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    price: float
    stock: int = 0
    image_url: str | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price: float
    stock: int
    image_url: str | None = None
    created_at: datetime
