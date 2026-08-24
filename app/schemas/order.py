from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrderCreate(BaseModel):
    """Places an order from whatever is currently in the user's cart."""
    pass


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    unit_price: float


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    total_amount: float
    created_at: datetime
    items: list[OrderItemResponse]
