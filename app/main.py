from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from app.db.connection import init_db
from app.routers import auth, cart, devices, health, orders, products
from app.seed import seed_demo_data, seed_products


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: create tables directly from models and seed sample
    init_db()
    seed_products()
    seed_demo_data()
    yield


app = FastAPI(
    title="Mobile Developer Assessment API",
    description=(
        "assignment. Built with FastAPI + SQLAlchemy"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": jsonable_encoder(exc.errors()),
        },
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
