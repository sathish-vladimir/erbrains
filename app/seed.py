"""Seeds sample data so every table has something to look at immediately
after a fresh install/migration - no manual API calls needed to populate
products, and a ready-to-use demo login for the rest of the tables
(devices, health_readings, cart_items, orders, order_items).

Run directly with: python -m app.seed
Also called automatically on app startup. Every function here is
idempotent (safe to run repeatedly) - it checks for existing rows before
inserting anything.
"""
import random
from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.db.connection import SessionLocal
from app.db.model import CartItem, Device, HealthReading, Order, OrderItem, Product, User

SAMPLE_PRODUCTS = [
    {
        "name": "FitRing Smart Ring",
        "description": "Wearable ring that tracks heart rate, SpO2 and steps.",
        "price": 129.99,
        "stock": 25,
        "image_url": "https://picsum.photos/seed/fitring/400",
    },
    {
        "name": "FitBand Pro",
        "description": "Wrist band wearable with heart-rate and sleep tracking.",
        "price": 89.5,
        "stock": 40,
        "image_url": "https://picsum.photos/seed/fitband/400",
    },
    {
        "name": "Wireless Charging Dock",
        "description": "Charging dock compatible with FitRing and FitBand devices.",
        "price": 24.0,
        "stock": 100,
        "image_url": "https://picsum.photos/seed/dock/400",
    },
    {
        "name": "Replacement Ring Band (Size Pack)",
        "description": "Set of silicone comfort bands, 3 sizes.",
        "price": 14.99,
        "stock": 60,
        "image_url": "https://picsum.photos/seed/band/400",
    },
]

# Matches the assignment PDF's dashboard example.
DEMO_EMAIL = "demo@erbrains.com"
DEMO_PASSWORD = "demo1234"
DEMO_DEVICE_ID = "FITRING-DEMO-001"


def seed_products():
    db = SessionLocal()
    try:
        if db.query(Product).count() > 0:
            return
        db.bulk_save_objects([Product(**p) for p in SAMPLE_PRODUCTS])
        db.commit()
    finally:
        db.close()


def seed_demo_data():
    """Creates a demo user with a device, a history of health readings
    (ending in the exact PDF dashboard values), one cart item, and one
    completed order - so devices/health_readings/cart_items/orders/
    order_items all have data to query right after setup, without having
    to drive the whole flow through Swagger by hand first.
    """
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == DEMO_EMAIL).first():
            return  # already seeded

        user = User(
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            full_name="Demo User",
        )
        db.add(user)
        db.flush()  # assigns user.id

        device = Device(
            device_id=DEMO_DEVICE_ID,
            user_id=user.id,
            name="Demo FitRing",
            battery=72,
            connection_status="connected",
        )
        db.add(device)
        db.flush()  # assigns device.id

        # ~3 days of readings (one every 2 hours) so /health/readings has
        # history to page through and /health/summary has something to
        # average, ending in the exact values shown in the assignment PDF.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        steps_so_far = 0
        for i in range(36, 0, -1):
            recorded_at = now - timedelta(hours=2 * i)
            steps_so_far += random.randint(150, 400)
            db.add(
                HealthReading(
                    client_reading_id=f"demo-seed-{i}",
                    user_id=user.id,
                    device_id=device.id,
                    heart_rate=random.randint(65, 95),
                    spo2=random.randint(95, 99),
                    steps=steps_so_far,
                    battery=max(20, 100 - i * 2),
                    recorded_at=recorded_at,
                )
            )
        # Final/current reading = the PDF's dashboard example exactly.
        db.add(
            HealthReading(
                client_reading_id="demo-seed-latest",
                user_id=user.id,
                device_id=device.id,
                heart_rate=78,
                spo2=98,
                steps=6420,
                battery=72,
                recorded_at=now,
            )
        )

        products = db.query(Product).order_by(Product.id).all()
        if len(products) >= 2:
            # One item left in the cart (not yet checked out).
            db.add(CartItem(user_id=user.id, product_id=products[0].id, quantity=1))

            # One completed order, so /orders has history to show too.
            ordered_product = products[1]
            order = Order(user_id=user.id, status="created", total_amount=ordered_product.price)
            db.add(order)
            db.flush()  # assigns order.id
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=ordered_product.id,
                    quantity=1,
                    unit_price=ordered_product.price,
                )
            )
            ordered_product.stock -= 1

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_products()
    seed_demo_data()
    print(f"Seeded products + demo data. Login with {DEMO_EMAIL} / {DEMO_PASSWORD}")
