from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.model import Device, HealthReading, User
from app.deps import get_current_user
from app.schemas.health import (
    HealthReadingBatchCreate,
    HealthReadingBatchResponse,
    HealthReadingCreate,
    HealthReadingResponse,
    HealthSummaryResponse,
)

router = APIRouter(prefix="/health", tags=["health"])


def _assert_device_owned(db: Session, device_id: int, user_id: int) -> Device:
    device = db.query(Device).filter(Device.id == device_id, Device.user_id == user_id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


def _insert_reading(db: Session, payload: HealthReadingCreate, user_id: int) -> HealthReading | None:
    """Returns the created row, or None if it was a duplicate
    (device_id, client_reading_id) already stored."""
    reading = HealthReading(
        client_reading_id=payload.client_reading_id,
        user_id=user_id,
        device_id=payload.device_id,
        heart_rate=payload.heart_rate,
        spo2=payload.spo2,
        steps=payload.steps,
        battery=payload.battery,
        recorded_at=payload.recorded_at,
    )
    db.add(reading)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(reading)
    return reading


@router.post("/readings", response_model=HealthReadingResponse, status_code=status.HTTP_201_CREATED)
def create_reading(
    payload: HealthReadingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _assert_device_owned(db, payload.device_id, current_user.id)
    reading = _insert_reading(db, payload, current_user.id)
    if reading is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reading with this client_reading_id already exists for this device",
        )
    return reading


@router.post("/readings/batch", response_model=HealthReadingBatchResponse, status_code=status.HTTP_201_CREATED)
def create_readings_batch(
    payload: HealthReadingBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Extra endpoint (beyond the spec's minimum list) that backs the offline
    sync queue: the app buffers readings locally while offline and flushes
    them here in one request once connectivity returns. Each reading is
    inserted independently so one duplicate/bad row doesn't fail the batch.
    """
    created: list[HealthReading] = []
    duplicates = 0
    for item in payload.readings:
        _assert_device_owned(db, item.device_id, current_user.id)
        reading = _insert_reading(db, item, current_user.id)
        if reading is None:
            duplicates += 1
        else:
            created.append(reading)

    return HealthReadingBatchResponse(created=created, duplicates_skipped=duplicates)


@router.get("/readings", response_model=list[HealthReadingResponse])
def list_readings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: int | None = Query(default=None),
    start: datetime | None = Query(default=None, description="Filter recorded_at >= start"),
    end: datetime | None = Query(default=None, description="Filter recorded_at <= end"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Paginated on purpose: the History screen must never pull an unbounded
    number of raw rows into the UI (see README - Local Health Data)."""
    q = db.query(HealthReading).filter(HealthReading.user_id == current_user.id)
    if device_id is not None:
        q = q.filter(HealthReading.device_id == device_id)
    if start is not None:
        q = q.filter(HealthReading.recorded_at >= start)
    if end is not None:
        q = q.filter(HealthReading.recorded_at <= end)

    return (
        q.order_by(HealthReading.recorded_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/summary", response_model=HealthSummaryResponse)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    period: str = Query(default="daily", pattern="^(daily|weekly)$"),
):
    period_end = datetime.now(timezone.utc).replace(tzinfo=None)
    period_start = period_end - (timedelta(days=1) if period == "daily" else timedelta(days=7))

    row = (
        db.query(
            func.avg(HealthReading.heart_rate),
            func.avg(HealthReading.spo2),
            func.coalesce(func.sum(HealthReading.steps), 0),
            func.count(HealthReading.id),
        )
        .filter(
            HealthReading.user_id == current_user.id,
            HealthReading.recorded_at >= period_start,
            HealthReading.recorded_at <= period_end,
        )
        .one()
    )
    avg_hr, avg_spo2, total_steps, count = row

    return HealthSummaryResponse(
        period_start=period_start,
        period_end=period_end,
        avg_heart_rate=round(avg_hr, 1) if avg_hr is not None else None,
        avg_spo2=round(avg_spo2, 1) if avg_spo2 is not None else None,
        total_steps=int(total_steps or 0),
        reading_count=int(count or 0),
    )
