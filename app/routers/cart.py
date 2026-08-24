from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.connection import get_db
from app.db.model import CartItem, Product, User
from app.deps import get_current_user
from app.schemas.cart import CartItemCreate, CartItemResponse, CartItemUpdate, CartResponse

router = APIRouter(prefix="/cart", tags=["cart"])


def _cart_total(items: list[CartItem]) -> float:
    return round(sum(item.quantity * item.product.price for item in items), 2)


@router.post("", response_model=CartItemResponse, status_code=status.HTTP_201_CREATED)
def add_to_cart(
    payload: CartItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if payload.quantity < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be >= 1")

    item = (
        db.query(CartItem)
        .filter(CartItem.user_id == current_user.id, CartItem.product_id == payload.product_id)
        .first()
    )
    if item:
        item.quantity += payload.quantity
    else:
        item = CartItem(user_id=current_user.id, product_id=payload.product_id, quantity=payload.quantity)
        db.add(item)

    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=CartResponse)
def get_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = (
        db.query(CartItem)
        .options(joinedload(CartItem.product))
        .filter(CartItem.user_id == current_user.id)
        .all()
    )
    return CartResponse(items=items, total_amount=_cart_total(items))


@router.patch("/{item_id}", response_model=CartItemResponse)
def update_cart_item(
    item_id: int,
    payload: CartItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Extra endpoint (not in the spec minimum list) so the Cart screen can
    change quantity without removing and re-adding the item."""
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    if payload.quantity < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be >= 1")

    item.quantity = payload.quantity
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_cart_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Extra endpoint - needed so users can remove items before checkout."""
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    db.delete(item)
    db.commit()
