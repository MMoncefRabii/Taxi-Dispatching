import { ApiError } from '../api/client';
import {
  flushLocationQueue,
  stopLocationTracking,
} from './tracker';
import { locationQueue } from './queue';
import type {
  LocationBatchRequest,
  LocationBatchResponse,
  QueuedLocationPayload,
} from '../api/client';

function point(recorded_at: number): QueuedLocationPayload {
  return { lat: 36.8, lng: 10.18, recorded_at };
}

afterEach(async () => {
  await stopLocationTracking();
  await locationQueue.clear();
  jest.clearAllMocks();
});

describe('location batch flush', () => {
  it('acknowledges accepted points and drops only rejected points', async () => {
    await locationQueue.enqueue(point(1));
    await locationQueue.enqueue(point(2));
    const sendBatch = jest.fn(
      async (_body: LocationBatchRequest): Promise<LocationBatchResponse> => ({
        accepted: 1,
        duplicates: 0,
        rejected: 1,
        rejections: [{ index: 1, reason: 'invalid_coordinates' }],
      }),
    );

    await flushLocationQueue(locationQueue, sendBatch);

    const state = await locationQueue.getState();
    expect(sendBatch).toHaveBeenCalledTimes(1);
    expect(state.entries).toEqual([]);
    expect(state.droppedCount).toBe(1);
    expect(state.lastSuccessfulSyncAt).not.toBeNull();
    expect(state.error).toBe('1 saved location point(s) were rejected.');
  });

  it('keeps points and schedules backoff after a server error', async () => {
    await locationQueue.enqueue(point(1));
    const sendBatch = jest.fn(async () => {
      throw new ApiError('Request failed.', 503);
    });

    await flushLocationQueue(locationQueue, sendBatch);

    const state = await locationQueue.getState();
    expect(state.entries).toHaveLength(1);
    expect(state.retryAttempt).toBe(1);
    expect(state.nextRetryAt).toBeGreaterThan(Date.now());
  });

  it('clears points when the token is rejected', async () => {
    await locationQueue.enqueue(point(1));
    const sendBatch = jest.fn(async () => {
      throw new ApiError('Session expired.', 401);
    });

    await flushLocationQueue(locationQueue, sendBatch);

    expect((await locationQueue.getState()).entries).toEqual([]);
  });

  it('allows only one network flush at a time', async () => {
    await locationQueue.enqueue(point(1));
    let finishRequest: (value: LocationBatchResponse) => void = () => {
      throw new Error('The batch request has not started.');
    };
    const sendBatch = jest.fn((_body: LocationBatchRequest) =>
      new Promise<LocationBatchResponse>(resolve => {
        finishRequest = value => resolve(value);
      }),
    );

    const first = flushLocationQueue(locationQueue, sendBatch);
    const second = flushLocationQueue(locationQueue, sendBatch);
    await new Promise<void>(resolve => setTimeout(resolve, 0));
    expect(sendBatch).toHaveBeenCalledTimes(1);

    finishRequest({
      accepted: 1,
      duplicates: 0,
      rejected: 0,
      rejections: [],
    });
    await Promise.all([first, second]);
    expect(sendBatch).toHaveBeenCalledTimes(1);
  });
});
