import {
  acknowledge,
  createEmptyQueue,
  drop,
  enqueue,
  LocationQueueStore,
  peekBatch,
  resetBackoff,
  runSingleFlush,
  scheduleBackoff,
} from './queue';
import type {
  QueueStorage,
  QueueState,
} from './queue';
import type { QueuedLocationPayload } from '../api/client';

function point(recorded_at: number): QueuedLocationPayload {
  return { lat: 36.8, lng: 10.18, recorded_at };
}

class MemoryStorage implements QueueStorage {
  values = new Map<string, string>();

  async getItem(key: string): Promise<string | null> {
    return this.values.get(key) ?? null;
  }

  async setItem(key: string, value: string): Promise<void> {
    this.values.set(key, value);
  }

  async removeItem(key: string): Promise<void> {
    this.values.delete(key);
  }
}

describe('location queue', () => {
  it('keeps points chronological and limits a peek to 50', () => {
    let state = createEmptyQueue();
    state = enqueue(state, point(300));
    state = enqueue(state, point(100));
    state = enqueue(state, point(200));

    expect(peekBatch(state).map(entry => entry.point.recorded_at)).toEqual([
      100,
      200,
      300,
    ]);

    for (let timestamp = 400; timestamp < 500; timestamp += 1) {
      state = enqueue(state, point(timestamp));
    }
    expect(peekBatch(state)).toHaveLength(50);
  });

  it('drops oldest entries at capacity and counts them', () => {
    let state = createEmptyQueue();
    for (let timestamp = 0; timestamp < 1001; timestamp += 1) {
      state = enqueue(state, point(timestamp));
    }

    expect(state.entries).toHaveLength(1000);
    expect(state.entries[0].point.recorded_at).toBe(1);
    expect(state.droppedCount).toBe(1);
  });

  it('persists and reloads the queue state', async () => {
    const storage = new MemoryStorage();
    const firstStore = new LocationQueueStore(storage, 'test_queue');
    const firstState = await firstStore.enqueue(point(123));
    const secondStore = new LocationQueueStore(storage, 'test_queue');

    expect(await secondStore.getState()).toEqual(firstState);
  });

  it('acknowledges successful entries and counts explicit drops', () => {
    let state = createEmptyQueue();
    state = enqueue(state, point(1));
    state = enqueue(state, point(2));
    const firstId = state.entries[0].id;
    const secondId = state.entries[1].id;

    state = acknowledge(state, [firstId]);
    state = drop(state, [secondId]);

    expect(state.entries).toEqual([]);
    expect(state.droppedCount).toBe(1);
  });

  it('backs off exponentially with jitter and resets after success', () => {
    let state: QueueState = createEmptyQueue();
    const delays: number[] = [];
    for (let attempt = 0; attempt < 8; attempt += 1) {
      const now = attempt * 1_000_000;
      state = scheduleBackoff(state, now, () => 0.5);
      delays.push(state.nextRetryAt! - now);
    }

    expect(delays.slice(0, 6)).toEqual([
      5000,
      10000,
      20000,
      40000,
      80000,
      160000,
    ]);
    expect(delays[7]).toBe(5 * 60 * 1000);
    expect(resetBackoff(state, 1234)).toMatchObject({
      retryAttempt: 0,
      nextRetryAt: null,
      lastSuccessfulSyncAt: 1234,
      error: null,
    });
  });

  it('allows only one concurrent flush', async () => {
    let finishFirst: (() => void) | undefined;
    const firstWork = new Promise<void>(resolve => {
      finishFirst = resolve;
    });
    const flush = jest.fn(async () => firstWork);

    const first = runSingleFlush(flush);
    const second = runSingleFlush(flush);
    expect(flush).toHaveBeenCalledTimes(1);

    finishFirst?.();
    await Promise.all([first, second]);
    expect(flush).toHaveBeenCalledTimes(1);
  });
});
