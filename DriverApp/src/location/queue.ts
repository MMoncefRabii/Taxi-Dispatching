import AsyncStorage from '@react-native-async-storage/async-storage';
import type { QueuedLocationPayload } from '../api/client';

export const LOCATION_QUEUE_STORAGE_KEY = 'driver_location_queue_v1';
export const LOCATION_QUEUE_CAP = 1000;
export const LOCATION_BATCH_SIZE = 50;
const BASE_BACKOFF_MS = 5000;
const MAX_BACKOFF_MS = 5 * 60 * 1000;
const BACKOFF_JITTER_RATIO = 0.2;

export interface QueueEntry {
  id: number;
  point: QueuedLocationPayload;
}

export interface QueueState {
  entries: QueueEntry[];
  nextId: number;
  droppedCount: number;
  retryAttempt: number;
  nextRetryAt: number | null;
  lastSuccessfulSyncAt: number | null;
  error: string | null;
}

export interface QueueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export function createEmptyQueue(): QueueState {
  return {
    entries: [],
    nextId: 1,
    droppedCount: 0,
    retryAttempt: 0,
    nextRetryAt: null,
    lastSuccessfulSyncAt: null,
    error: null,
  };
}

function chronologicalEntries(entries: QueueEntry[]): QueueEntry[] {
  return [...entries].sort(
    (left, right) =>
      left.point.recorded_at - right.point.recorded_at || left.id - right.id,
  );
}

export function enqueue(
  state: QueueState,
  point: QueuedLocationPayload,
): QueueState {
  const entries = chronologicalEntries([
    ...state.entries,
    { id: state.nextId, point },
  ]);
  const overflow = Math.max(0, entries.length - LOCATION_QUEUE_CAP);
  return {
    ...state,
    entries: entries.slice(overflow),
    nextId: state.nextId + 1,
    droppedCount: state.droppedCount + overflow,
  };
}

export function peekBatch(
  state: QueueState,
  limit = LOCATION_BATCH_SIZE,
): QueueEntry[] {
  const safeLimit = Math.min(
    LOCATION_BATCH_SIZE,
    Math.max(0, Math.floor(limit)),
  );
  return chronologicalEntries(state.entries).slice(0, safeLimit);
}

export function acknowledge(
  state: QueueState,
  ids: readonly number[],
): QueueState {
  const acknowledged = new Set(ids);
  return {
    ...state,
    entries: state.entries.filter(entry => !acknowledged.has(entry.id)),
  };
}

export function drop(
  state: QueueState,
  ids: readonly number[],
): QueueState {
  const dropped = new Set(ids);
  const remaining = state.entries.filter(entry => !dropped.has(entry.id));
  return {
    ...state,
    entries: remaining,
    droppedCount: state.droppedCount + state.entries.length - remaining.length,
  };
}

export function scheduleBackoff(
  state: QueueState,
  now: number,
  random: () => number = Math.random,
): QueueState {
  const baseDelay = Math.min(
    MAX_BACKOFF_MS,
    BASE_BACKOFF_MS * 2 ** Math.min(state.retryAttempt, 16),
  );
  const jitter = 1 - BACKOFF_JITTER_RATIO + random() * BACKOFF_JITTER_RATIO * 2;
  return {
    ...state,
    retryAttempt: state.retryAttempt + 1,
    nextRetryAt: now + Math.min(MAX_BACKOFF_MS, Math.floor(baseDelay * jitter)),
  };
}

export function resetBackoff(
  state: QueueState,
  successfulAt: number | null,
): QueueState {
  return {
    ...state,
    retryAttempt: 0,
    nextRetryAt: null,
    lastSuccessfulSyncAt: successfulAt ?? state.lastSuccessfulSyncAt,
    error: null,
  };
}

export function setQueueError(state: QueueState, error: string): QueueState {
  return { ...state, error };
}

function isQueueState(value: unknown): value is QueueState {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const state = value as Partial<QueueState>;
  return (
    Array.isArray(state.entries) &&
    Number.isInteger(state.nextId) &&
    Number.isInteger(state.droppedCount) &&
    Number.isInteger(state.retryAttempt) &&
    (state.nextRetryAt === null || typeof state.nextRetryAt === 'number') &&
    (state.lastSuccessfulSyncAt === null ||
      typeof state.lastSuccessfulSyncAt === 'number') &&
    (state.error === null || typeof state.error === 'string') &&
    state.entries.every(
      entry =>
        Number.isInteger(entry.id) &&
        typeof entry.point?.lat === 'number' &&
        typeof entry.point?.lng === 'number' &&
        typeof entry.point?.recorded_at === 'number',
    )
  );
}

export class LocationQueueStore {
  private state: QueueState | null = null;
  private loadPromise: Promise<QueueState> | null = null;
  private mutations: Promise<void> = Promise.resolve();

  constructor(
    private readonly storage: QueueStorage = AsyncStorage,
    private readonly storageKey = LOCATION_QUEUE_STORAGE_KEY,
  ) {}

  async getState(): Promise<QueueState> {
    await this.mutations;
    return this.loadState();
  }

  private async loadState(): Promise<QueueState> {
    if (this.state) {
      return this.state;
    }
    if (!this.loadPromise) {
      this.loadPromise = this.loadFromStorage();
    }
    try {
      this.state = await this.loadPromise;
      return this.state;
    } finally {
      this.loadPromise = null;
    }
  }

  async enqueue(point: QueuedLocationPayload): Promise<QueueState> {
    return this.update(state => enqueue(state, point));
  }

  async acknowledge(ids: readonly number[]): Promise<QueueState> {
    return this.update(state => acknowledge(state, ids));
  }

  async drop(ids: readonly number[]): Promise<QueueState> {
    return this.update(state => drop(state, ids));
  }

  async update(
    transform: (state: QueueState) => QueueState,
  ): Promise<QueueState> {
    let updatedState: QueueState | null = null;
    const operation = this.mutations.then(async () => {
      const nextState = transform(await this.loadState());
      await this.storage.setItem(this.storageKey, JSON.stringify(nextState));
      this.state = nextState;
      updatedState = nextState;
    });
    this.mutations = operation.then(
      () => undefined,
      () => undefined,
    );
    await operation;
    if (updatedState === null) {
      throw new Error('Location queue update did not complete.');
    }
    return updatedState;
  }

  async clear(): Promise<void> {
    const operation = this.mutations.then(async () => {
      await this.storage.removeItem(this.storageKey);
      this.state = createEmptyQueue();
      this.loadPromise = null;
    });
    this.mutations = operation.then(
      () => undefined,
      () => undefined,
    );
    await operation;
  }

  async peek(limit = LOCATION_BATCH_SIZE): Promise<QueueEntry[]> {
    return peekBatch(await this.getState(), limit);
  }

  private async loadFromStorage(): Promise<QueueState> {
    const serialized = await this.storage.getItem(this.storageKey);
    if (serialized === null) {
      return createEmptyQueue();
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(serialized);
    } catch {
      throw new Error('Stored location queue is unreadable and was not cleared.');
    }
    if (!isQueueState(parsed)) {
      throw new Error('Stored location queue is invalid and was not cleared.');
    }
    return parsed;
  }
}

let activeFlush: Promise<void> | null = null;

export function runSingleFlush(flush: () => Promise<void>): Promise<void> {
  if (activeFlush) {
    return activeFlush;
  }
  const currentFlush = flush().finally(() => {
    if (activeFlush === currentFlush) {
      activeFlush = null;
    }
  });
  activeFlush = currentFlush;
  return currentFlush;
}

export const locationQueue = new LocationQueueStore();
