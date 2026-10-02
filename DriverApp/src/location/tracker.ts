import Geolocation from 'react-native-geolocation-service';
import {
  ApiResponse,
  LocationPayload,
  postJson,
} from '../api/client';
import type { GeoPosition } from 'react-native-geolocation-service';

let activeWatchId: number | null = null;

export function startLocationTracking(
  onSent: (location: LocationPayload) => void,
  onSyncIssue: (hasIssue: boolean) => void,
): void {
  stopLocationTracking();
  let consecutiveFailures = 0;
  let sending = false;

  const sendPosition = async (position: GeoPosition) => {
    if (sending) {
      return;
    }

    const { latitude, longitude, speed, heading, accuracy } = position.coords;
    const payload: LocationPayload = {
      lat: latitude,
      lng: longitude,
      ...(speed == null ? {} : { speed }),
      ...(heading == null ? {} : { heading }),
      ...(accuracy == null ? {} : { accuracy }),
      recorded_at: Math.floor(position.timestamp / 1000),
    };

    sending = true;
    try {
      const result = await postJson<ApiResponse>('/location', payload);
      consecutiveFailures = 0;
      onSyncIssue(false);
      if (result.ok) {
        onSent(payload);
      }
    } catch (error) {
      console.warn('Location update failed:', error);
      consecutiveFailures += 1;
      if (consecutiveFailures >= 3) {
        onSyncIssue(true);
      }
    } finally {
      sending = false;
    }
  };

  const handleLocationError = (error: { code: number; message: string }) => {
    console.warn('Location watcher error:', error);
  };

  activeWatchId = Geolocation.watchPosition(
    sendPosition,
    handleLocationError,
    {
      enableHighAccuracy: true,
      distanceFilter: 0,
      interval: 7000,
      fastestInterval: 5000,
    },
  );

  Geolocation.getCurrentPosition(sendPosition, handleLocationError, {
    enableHighAccuracy: true,
    maximumAge: 0,
    timeout: 15000,
    forceRequestLocation: true,
    showLocationDialog: true,
  });
}

export function stopLocationTracking(): void {
  if (activeWatchId !== null) {
    Geolocation.clearWatch(activeWatchId);
    activeWatchId = null;
  }
}