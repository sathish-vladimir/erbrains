from pydantic import BaseModel, ConfigDict

from app.schemas.product import ProductResponse


class CartItemCreate(BaseModel):
    product_id: int
    quantity: int = 1


class CartItemUpdate(BaseModel):
    quantity: int


class CartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: int
    product: ProductResponse


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    total_amount: float
