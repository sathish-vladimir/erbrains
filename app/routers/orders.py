from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.connection import get_db
from app.db.model import CartItem, Order, OrderItem, User
from app.deps import get_current_user
from app.schemas.order import OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def place_order(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Places an order from whatever is currently in the user's cart.

    Runs as a single DB transaction: stock is checked and decremented,
    order + order_items are written, and the cart is cleared together, or
    nothing is written at all if any step fails (e.g. insufficient stock).
    No real payment gateway - see assignment scope note.
    """
    cart_items = (
        db.query(CartItem)
        .options(joinedload(CartItem.product))
        .filter(CartItem.user_id == current_user.id)
        .all()
    )
    if not cart_items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    for ci in cart_items:
        if ci.product.stock < ci.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for '{ci.product.name}'",
            )

    total_amount = round(sum(ci.quantity * ci.product.price for ci in cart_items), 2)
    order = Order(user_id=current_user.id, status="created", total_amount=total_amount)
    db.add(order)
    db.flush()  # assigns order.id without committing yet

    for ci in cart_items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=ci.product_id,
                quantity=ci.quantity,
                unit_price=ci.product.price,
            )
        )
        ci.product.stock -= ci.quantity
        db.delete(ci)

    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=list[OrderResponse])
def list_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.user_id == current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
