import BackgroundService from 'react-native-background-actions';
import { Platform } from 'react-native';
import Geolocation from 'react-native-geolocation-service';
import type { GeoPosition } from 'react-native-geolocation-service';
import { ApiError, postJson } from '../api/client';
import type {
  LocationBatchRequest,
  LocationBatchResponse,
  LocationPayload,
  QueuedLocationPayload,
} from '../api/client';
import {
  LOCATION_BATCH_SIZE,
  locationQueue,
  resetBackoff,
  runSingleFlush,
  scheduleBackoff,
  setQueueError,
} from './queue';
import type { LocationQueueStore, QueueState } from './queue';

export interface TrackerCallbacks {
  onLocation: (location: LocationPayload) => void;
  onQueueState: (state: QueueState) => void;
  onError: (message: string | null) => void;
}

type BatchSender = (
  body: LocationBatchRequest,
) => Promise<LocationBatchResponse>;

const trackingOptions = {
  taskName: 'FleetLocationTracking',
  taskTitle: 'Fleet Tracker',
  taskDesc: 'Fleet Tracker is sharing your location',
  taskIcon: { name: 'ic_launcher', type: 'mipmap' },
  color: '#215b3c',
  foregroundServiceType: ['location'] as Array<'location'>,
};

let activeWatchId: number | null = null;
let stopTask: (() => void) | null = null;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let activeCallbacks: TrackerCallbacks | null = null;

function isBatchResponse(
  value: unknown,
  batchSize: number,
): value is LocationBatchResponse {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const response = value as Partial<LocationBatchResponse>;
  if (
    typeof response.accepted !== 'number' ||
    !Number.isInteger(response.accepted) ||
    response.accepted < 0 ||
    typeof response.duplicates !== 'number' ||
    !Number.isInteger(response.duplicates) ||
    response.duplicates < 0 ||
    typeof response.rejected !== 'number' ||
    !Number.isInteger(response.rejected) ||
    response.rejected < 0 ||
    !Array.isArray(response.rejections)
  ) {
    return false;
  }

  const rejections = response.rejections as unknown[];
  if (
    rejections.length !== response.rejected ||
    response.accepted + response.duplicates + response.rejected !== batchSize ||
    !rejections.every(
      rejection =>
        typeof rejection === 'object' &&
        rejection !== null &&
        'index' in rejection &&
        'reason' in rejection &&
        Number.isInteger(rejection.index) &&
        typeof rejection.index === 'number' &&
        rejection.index >= 0 &&
        rejection.index < batchSize &&
        typeof rejection.reason === 'string',
    )
  ) {
    return false;
  }
  return new Set(
    rejections.map(rejection => (rejection as { index: number }).index),
  ).size === rejections.length;
}

function notifyQueueState(state: QueueState): void {
  activeCallbacks?.onQueueState(state);
}

function scheduleRetry(state: QueueState): void {
  if (retryTimer !== null) {
    clearTimeout(retryTimer);
  }
  if (state.nextRetryAt === null) {
    retryTimer = null;
    return;
  }
  retryTimer = setTimeout(() => {
    retryTimer = null;
    flushLocationQueue().catch(() => {
      activeCallbacks?.onError('Unable to update the saved location queue.');
    });
  }, Math.max(0, state.nextRetryAt - Date.now()));
}

async function saveFlushFailure(
  queue: LocationQueueStore,
  message: string,
): Promise<void> {
  const state = await queue.update(current =>
    setQueueError(scheduleBackoff(current, Date.now()), message),
  );
  notifyQueueState(state);
  activeCallbacks?.onError(message);
  scheduleRetry(state);
}

export async function flushLocationQueue(
  queue: LocationQueueStore = locationQueue,
  sendBatch: BatchSender = body =>
    postJson<LocationBatchResponse>('/location/batch', body),
): Promise<void> {
  await runSingleFlush(async () => {
    let current = await queue.getState();
    while (current.entries.length > 0) {
      if (current.nextRetryAt !== null && current.nextRetryAt > Date.now()) {
        scheduleRetry(current);
        return;
      }

      const batch = await queue.peek(LOCATION_BATCH_SIZE);
      if (batch.length === 0) {
        return;
      }

      let response: LocationBatchResponse;
      try {
        response = await sendBatch({
          points: batch.map(entry => entry.point),
        });
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          await queue.clear();
          notifyQueueState(await queue.getState());
          activeCallbacks?.onError('Session expired. Enter your driver token again.');
          return;
        }
        const message =
          error instanceof ApiError && error.status === 429
            ? 'The server is limiting location updates. Retrying shortly.'
            : error instanceof ApiError &&
                error.status !== undefined &&
                error.status >= 500
              ? 'The server is unavailable. Saved locations will retry.'
              : 'Unable to sync saved locations. Check the network and retry.';
        await saveFlushFailure(queue, message);
        return;
      }

      if (!isBatchResponse(response, batch.length)) {
        await saveFlushFailure(
          queue,
          'The server returned an invalid location batch response.',
        );
        return;
      }

      const rejectedIndexes = new Set(
        response.rejections.map(rejection => rejection.index),
      );
      const rejectedIds = batch
        .filter((_, index) => rejectedIndexes.has(index))
        .map(entry => entry.id);
      const acknowledgedIds = batch
        .filter((_, index) => !rejectedIndexes.has(index))
        .map(entry => entry.id);

      current = await queue.drop(rejectedIds);
      current = await queue.acknowledge(acknowledgedIds);
      current = await queue.update(state => {
        const reset = resetBackoff(
          state,
          response.accepted + response.duplicates > 0 ? Date.now() : null,
        );
        return response.rejected > 0
          ? setQueueError(
              reset,
              `${response.rejected} saved location point(s) were rejected.`,
            )
          : reset;
      });
      notifyQueueState(current);
      if (response.rejected > 0) {
        activeCallbacks?.onError(
          `${response.rejected} saved location point(s) were rejected.`,
        );
      } else {
        activeCallbacks?.onError(null);
      }
      if (current.entries.length === 0) {
        if (retryTimer !== null) {
          clearTimeout(retryTimer);
          retryTimer = null;
        }
        return;
      }
    }
  });
}

function reportLocationError(): void {
  activeCallbacks?.onError(
    'Unable to obtain location. Check device location settings.',
  );
}

function enqueuePosition(position: GeoPosition): void {
  const { latitude, longitude, speed, heading, accuracy } = position.coords;
  const point: QueuedLocationPayload = {
    lat: latitude,
    lng: longitude,
    ...(speed == null ? {} : { speed }),
    ...(heading == null ? {} : { heading }),
    ...(accuracy == null ? {} : { accuracy }),
    recorded_at: Math.floor(position.timestamp / 1000),
  };

  const enqueueTask = async () => {
    try {
      const previousState = await locationQueue.getState();
      let state = await locationQueue.enqueue(point);
      if (state.droppedCount > previousState.droppedCount) {
        state = await locationQueue.update(current =>
          setQueueError(
            current,
            `${state.droppedCount} oldest location point(s) were dropped because the queue is full.`,
          ),
        );
        activeCallbacks?.onError(state.error);
      }
      notifyQueueState(state);
      activeCallbacks?.onLocation(point);
      await flushLocationQueue();
    } catch {
      activeCallbacks?.onError(
        'Unable to save this location on the device. Check local storage.',
      );
    }
  };
  enqueueTask().catch(() => {
    activeCallbacks?.onError('Unable to process this location.');
  });
}

function startGeolocationWatch(): void {
  if (activeWatchId !== null) {
    return;
  }
  activeWatchId = Geolocation.watchPosition(
    enqueuePosition,
    reportLocationError,
    {
      enableHighAccuracy: true,
      distanceFilter: 0,
      interval: 7000,
      fastestInterval: 5000,
    },
  );
  Geolocation.getCurrentPosition(enqueuePosition, reportLocationError, {
    enableHighAccuracy: true,
    maximumAge: 0,
    timeout: 15000,
    forceRequestLocation: true,
    showLocationDialog: true,
  });
}

async function backgroundTrackingTask(): Promise<void> {
  try {
    await new Promise<void>(resolve => {
      stopTask = resolve;
      startGeolocationWatch();
    });
  } finally {
    stopTask = null;
    if (activeWatchId !== null) {
      Geolocation.clearWatch(activeWatchId);
      activeWatchId = null;
    }
  }
}

export async function startLocationTracking(
  callbacks: TrackerCallbacks,
): Promise<void> {
  activeCallbacks = callbacks;
  notifyQueueState(await locationQueue.getState());

  if (Platform.OS === 'android') {
    if (!BackgroundService.isRunning()) {
      await BackgroundService.start(backgroundTrackingTask, trackingOptions);
    }
  } else {
    startGeolocationWatch();
  }
  await flushLocationQueue();
}

export async function stopLocationTracking(): Promise<void> {
  if (retryTimer !== null) {
    clearTimeout(retryTimer);
    retryTimer = null;
  }
  stopTask?.();
  try {
    if (Platform.OS === 'android' && BackgroundService.isRunning()) {
      await BackgroundService.stop();
    }
  } finally {
    try {
      if (activeWatchId !== null) {
        Geolocation.clearWatch(activeWatchId);
        activeWatchId = null;
      }
    } finally {
      activeCallbacks = null;
    }
  }
}
