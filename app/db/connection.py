from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables directly from models.

    Handy for local/dev. In staging/production, prefer running
    `alembic upgrade head` (see /alembic) instead of relying on this.
    """
    # Import models before create_all so SQLAlchemy knows all tables.
    from app.db.model import User, Device, HealthReading, Product, CartItem, Order, OrderItem  # noqa: F401
    Base.metadata.create_all(bind=engine)
