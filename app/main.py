from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db.connection import init_db
from app.routers import auth, cart, devices, health, orders, products
from app.seed import seed_demo_data, seed_products


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: create tables directly from models and seed sample
    # products. In staging/production run `alembic upgrade head` instead
    # (see README - Deployment) and this create_all becomes a no-op.
    init_db()
    seed_products()
    seed_demo_data()
    yield


app = FastAPI(
    title="Senior Mobile Developer Assessment API",
    description=(
        "Backend for the ERBrains wearable health + shopping take-home "
        "assignment. Built with FastAPI + SQLAlchemy instead of the "
        "suggested Node.js/NestJS stack - see README for the reasoning."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Wide-open CORS for local development against a Flutter app running on an
# emulator / a device on the same network. Tighten this for real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request, exc):
    # Returns a flatter, more mobile-friendly error shape than FastAPI's default.
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": exc.errors()},
    )


@app.get("/health", tags=["meta"])
def health_check():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(health.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(orders.router)
