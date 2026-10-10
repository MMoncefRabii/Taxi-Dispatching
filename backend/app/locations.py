"""Pure validation helpers for driver location samples."""

from dataclasses import dataclass
from enum import Enum
import math


class LocationReason(str, Enum):
    INVALID_REQUEST = "invalid_request"
    INVALID_COORDINATES = "invalid_coordinates"
    INVALID_HEADING = "invalid_heading"
    INVALID_SPEED = "invalid_speed"
    LOW_ACCURACY = "low_accuracy"
    TIMESTAMP_TOO_FUTURE = "timestamp_too_future"
    TIMESTAMP_TOO_OLD = "timestamp_too_old"
    TOO_FREQUENT = "too_frequent"
    IMPLAUSIBLE_SPEED = "implausible_speed"
    REQUEST_TOO_LARGE = "request_too_large"


@dataclass(frozen=True)
class LocationSample:
    lat: float
    lng: float
    recorded_at: float
    speed: float | None = None
    heading: float | None = None
    accuracy: float | None = None


@dataclass(frozen=True)
class LocationLimits:
    max_future_seconds: float
    max_age_seconds: float
    min_interval_seconds: float
    max_speed_kmh: float
    max_accuracy_m: float


def haversine_distance_m(first: LocationSample, second: LocationSample) -> float:
    earth_radius_m = 6_371_000
    lat1 = math.radians(first.lat)
    lat2 = math.radians(second.lat)
    delta_lat = lat2 - lat1
    delta_lng = math.radians(second.lng - first.lng)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return earth_radius_m * 2 * math.asin(math.sqrt(min(1.0, value)))


def validate_location(
    point: LocationSample,
    *,
    now: float,
    previous: LocationSample | None,
    limits: LocationLimits,
) -> LocationReason | None:
    values = (point.lat, point.lng, point.recorded_at)
    if not all(math.isfinite(value) for value in values):
        return LocationReason.INVALID_COORDINATES
    if not -90 <= point.lat <= 90 or not -180 <= point.lng <= 180:
        return LocationReason.INVALID_COORDINATES
    if point.speed is not None and (
        not math.isfinite(point.speed)
        or point.speed < 0
        or point.speed > limits.max_speed_kmh / 3.6
    ):
        return LocationReason.INVALID_SPEED
    if point.heading is not None and (
        not math.isfinite(point.heading) or not 0 <= point.heading <= 360
    ):
        return LocationReason.INVALID_HEADING
    if point.accuracy is not None and (
        not math.isfinite(point.accuracy)
        or point.accuracy < 0
        or point.accuracy > limits.max_accuracy_m
    ):
        return LocationReason.LOW_ACCURACY
    if point.recorded_at > now + limits.max_future_seconds:
        return LocationReason.TIMESTAMP_TOO_FUTURE
    if point.recorded_at < now - limits.max_age_seconds:
        return LocationReason.TIMESTAMP_TOO_OLD

    if previous is not None:
        elapsed_seconds = point.recorded_at - previous.recorded_at
        if elapsed_seconds < limits.min_interval_seconds:
            return LocationReason.TOO_FREQUENT
        distance_m = haversine_distance_m(previous, point)
        speed_kmh = distance_m / elapsed_seconds * 3.6
        if speed_kmh > limits.max_speed_kmh:
            return LocationReason.IMPLAUSIBLE_SPEED

    return None
