import AsyncStorage from '@react-native-async-storage/async-storage';
import { getBackendUrl } from './constants';

export interface StatusPayload {
  online: boolean;
}

export interface LocationPayload {
  lat: number;
  lng: number;
  speed?: number;
  heading?: number;
  accuracy?: number;
  recorded_at?: number;
}

export interface ApiResponse {
  ok: boolean;
  ignored?: string;
}

export type QueuedLocationPayload = LocationPayload & { recorded_at: number };

export interface LocationBatchRequest {
  points: QueuedLocationPayload[];
}

export interface LocationBatchResponse {
  accepted: number;
  duplicates: number;
  rejected: number;
  rejections: Array<{ index: number; reason: string }>;
}

const REQUEST_TIMEOUT_MS = 10000;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

type UnauthorizedHandler = (() => void | Promise<void>) | null;
let unauthorizedHandler: UnauthorizedHandler = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler;
}

export async function postJson<T>(
  path: '/status' | '/location' | '/location/batch',
  body: StatusPayload | LocationPayload | LocationBatchRequest,
): Promise<T> {
  const token = await AsyncStorage.getItem('driver_token');
  if (!token) {
    throw new ApiError('Driver token is missing.');
  }

  const baseUrl = await getBackendUrl();
  let response: Response;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-token': token,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new ApiError(
        'Request timed out. Check that the backend is running and the URL is correct.',
      );
    }
    throw new ApiError(
      'Unable to reach the backend. Check that it is running and the URL is correct.',
    );
  } finally {
    clearTimeout(timeout);
  }

  if (response.status === 401) {
    await unauthorizedHandler?.();
    throw new ApiError('Session expired.', 401);
  }

  if (!response.ok) {
    throw new ApiError(
      `Request failed with status ${response.status}.`,
      response.status,
    );
  }

  return (await response.json()) as T;
}