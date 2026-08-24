from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.model import Device, User
from app.deps import get_current_user
from app.schemas.device import DeviceCreate, DeviceResponse, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registers (or re-links) a wearable device to the current user.

    In the Flutter app this is called once the mock/real wearable connects
    for the first time, so the backend knows which device_id belongs to
    which user before health readings start syncing.
    """
    existing = db.query(Device).filter(Device.device_id == payload.device_id).first()
    if existing:
        if existing.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Device already registered to another user",
            )
        existing.name = payload.name
        existing.battery = payload.battery
        existing.connection_status = payload.connection_status
        db.commit()
        db.refresh(existing)
        return existing

    device = Device(
        device_id=payload.device_id,
        user_id=current_user.id,
        name=payload.name,
        battery=payload.battery,
        connection_status=payload.connection_status,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.get("", response_model=list[DeviceResponse])
def list_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Device)
        .filter(Device.user_id == current_user.id)
        .order_by(Device.created_at.desc())
        .all()
    )


@router.patch("/{device_id}", response_model=DeviceResponse)
def update_device(
    device_id: int,
    payload: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Extra endpoint (not in the spec's minimum list) used by the app to
    push connection-status / battery changes as the wearable connects,
    disconnects, and reconnects."""
    device = (
        db.query(Device)
        .filter(Device.id == device_id, Device.user_id == current_user.id)
        .first()
    )
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(device, field, value)

    db.commit()
    db.refresh(device)
    return device
