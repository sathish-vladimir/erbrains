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


def _assert_device_owned(
    db: Session,
    device_id: int,
    user_id: int,
) -> Device:
    device = (
        db.query(Device)
        .filter(
            Device.id == device_id,
            Device.user_id == user_id,
        )
        .first()
    )

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    return device


def _insert_reading(
    db: Session,
    payload: HealthReadingCreate,
    user_id: int,
) -> HealthReading | None:
    """
    Insert a health reading.

    Returns:
        HealthReading -> newly created reading
        None          -> duplicate client_reading_id

    The database UNIQUE constraint is the final protection
    against duplicate readings.
    """

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


@router.post(
    "/readings",
    response_model=HealthReadingResponse,
)
def create_reading(
    payload: HealthReadingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create one health reading.

    This endpoint is idempotent.

    If the same client_reading_id is sent again,
    the existing server record is returned instead of
    returning HTTP 409.

    This is important for offline-first synchronization because
    the client may retry a request when the previous request
    actually reached the server but the response was lost.
    """

    # Make sure the device belongs to the logged-in user.
    _assert_device_owned(
        db,
        payload.device_id,
        current_user.id,
    )

    # Try to insert.
    reading = _insert_reading(
        db,
        payload,
        current_user.id,
    )

    # New reading successfully inserted.
    if reading is not None:
        return reading

    # ---------------------------------------------------------
    # Duplicate reading
    # ---------------------------------------------------------
    #
    # The INSERT failed because client_reading_id already exists.
    #
    # Find the existing record and return it as SUCCESS.
    #
    existing = (
        db.query(HealthReading)
        .filter(
            HealthReading.client_reading_id
            == payload.client_reading_id,
            HealthReading.device_id == payload.device_id,
            HealthReading.user_id == current_user.id,
        )
        .first()
    )

    if existing is not None:
        return existing

    # If we reached here, the INSERT failed for some other
    # integrity reason.
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to save health reading",
    )


@router.post(
    "/readings/batch",
    response_model=HealthReadingBatchResponse,
)
def create_readings_batch(
    payload: HealthReadingBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Insert multiple health readings.

    Duplicate readings are skipped instead of failing
    the complete batch.

    This is useful for offline synchronization.
    """

    created: list[HealthReading] = []
    duplicates = 0

    for item in payload.readings:

        # Make sure every device belongs to the logged-in user.
        _assert_device_owned(
            db,
            item.device_id,
            current_user.id,
        )

        reading = _insert_reading(
            db,
            item,
            current_user.id,
        )

        if reading is None:
            duplicates += 1
        else:
            created.append(reading)

    return HealthReadingBatchResponse(
        created=created,
        duplicates_skipped=duplicates,
    )


@router.get(
    "/readings",
    response_model=list[HealthReadingResponse],
)
def list_readings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    device_id: int | None = Query(default=None),
    start: datetime | None = Query(
        default=None,
        description="Filter recorded_at >= start",
    ),
    end: datetime | None = Query(
        default=None,
        description="Filter recorded_at <= end",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
):
    """
    Return paginated health readings for the logged-in user.
    """

    q = (
        db.query(HealthReading)
        .filter(
            HealthReading.user_id == current_user.id
        )
    )

    if device_id is not None:
        q = q.filter(
            HealthReading.device_id == device_id
        )

    if start is not None:
        q = q.filter(
            HealthReading.recorded_at >= start
        )

    if end is not None:
        q = q.filter(
            HealthReading.recorded_at <= end
        )

    return (
        q.order_by(
            HealthReading.recorded_at.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get(
    "/summary",
    response_model=HealthSummaryResponse,
)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    period: str = Query(
        default="daily",
        pattern="^(daily|weekly)$",
    ),
):
    """
    Return health summary for the selected period.
    """

    period_end = datetime.now(
        timezone.utc
    ).replace(tzinfo=None)

    period_start = period_end - (
        timedelta(days=1)
        if period == "daily"
        else timedelta(days=7)
    )

    row = (
        db.query(
            func.avg(
                HealthReading.heart_rate
            ),
            func.avg(
                HealthReading.spo2
            ),
            func.coalesce(
                func.sum(
                    HealthReading.steps
                ),
                0,
            ),
            func.count(
                HealthReading.id
            ),
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
        avg_heart_rate=(
            round(avg_hr, 1)
            if avg_hr is not None
            else None
        ),
        avg_spo2=(
            round(avg_spo2, 1)
            if avg_spo2 is not None
            else None
        ),
        total_steps=int(
            total_steps or 0
        ),
        reading_count=int(
            count or 0
        ),
    )