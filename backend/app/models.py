"""SQLAlchemy models for the multi-tenant Fleet Tracker foundation."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Center(Base):
    __tablename__ = "centers"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Africa/Tunis")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admins: Mapped[list[Admin]] = relationship(back_populates="center")
    drivers: Mapped[list[Driver]] = relationship(back_populates="center")
    zones: Mapped[list[Zone]] = relationship(back_populates="center")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="center")


class SuperAdmin(Base):
    __tablename__ = "super_admins"
    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Admin(Base):
    __tablename__ = "admins"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_admin_email_lowercase"),
        UniqueConstraint("email", name="uq_admin_email"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    center_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("centers.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="center_admin")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    center: Mapped[Center] = relationship(back_populates="admins")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="actor_admin")
    sessions: Mapped[list[AdminSession]] = relationship(back_populates="admin")


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        Index("ix_admin_sessions_token_hash", "token_hash", unique=True),
        Index("ix_admin_sessions_admin_id", "admin_id"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admins.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admin: Mapped[Admin] = relationship(back_populates="sessions")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = uuid_pk()
    center_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("centers.id"), nullable=False, index=True)
    actor_admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admins.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    center: Mapped[Center] = relationship(back_populates="audit_logs")
    actor_admin: Mapped[Admin] = relationship(back_populates="audit_logs")


class Driver(Base):
    __tablename__ = "drivers"
    id: Mapped[uuid.UUID] = uuid_pk()
    center_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("centers.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    center: Mapped[Center] = relationship(back_populates="drivers")
    vehicle: Mapped[Vehicle | None] = relationship(back_populates="driver", uselist=False)
    locations: Mapped[list[DriverLocation]] = relationship(back_populates="driver")
    status_logs: Mapped[list[DriverStatusLog]] = relationship(back_populates="driver")


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[uuid.UUID] = uuid_pk()
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"), nullable=False, unique=True, index=True)
    taxi_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    plate_number: Mapped[str] = mapped_column(String(50), nullable=False)
    type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    driver: Mapped[Driver] = relationship(back_populates="vehicle")


class DriverLocation(Base):
    __tablename__ = "driver_locations"
    id: Mapped[uuid.UUID] = uuid_pk()
    center_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("centers.id"), nullable=False, index=True)
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"), nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    driver: Mapped[Driver] = relationship(back_populates="locations")


class DriverStatusLog(Base):
    __tablename__ = "driver_status_logs"
    id: Mapped[uuid.UUID] = uuid_pk()
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("drivers.id"), nullable=False, index=True)
    online: Mapped[bool] = mapped_column(Boolean, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    driver: Mapped[Driver] = relationship(back_populates="status_logs")


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("center_id", "code", name="uq_zone_center_code"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    center_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("centers.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    boundary: Mapped[str | None] = mapped_column(Text, nullable=True)
    center: Mapped[Center] = relationship(back_populates="zones")