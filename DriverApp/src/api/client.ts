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

export interface DriverCreationRequest {
  adminKey: string;
  name: string;
  phone: string;
}

export async function createDriverToken({
  adminKey,
  name,
  phone,
}: DriverCreationRequest): Promise<string> {
  const baseUrl = await getBackendUrl();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${baseUrl}/admin/drivers`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-admin-key': adminKey,
      },
      body: JSON.stringify({ name, phone }),
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `Request failed with status ${response.status}.`;
      try {
        const payload = (await response.json()) as { detail?: string };
        if (payload.detail) {
          detail = payload.detail;
        }
      } catch {
        // Keep the status-based error if the server did not return JSON.
      }
      throw new ApiError(detail, response.status);
    }

    const payload = (await response.json()) as {
      token?: string;
      id?: string;
      name?: string;
    };
    if (!payload.token) {
      throw new ApiError('The server did not return a driver token.');
    }
    return payload.token;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new ApiError(
        'Request timed out. Check that the backend is running and the URL is correct.',
      );
    }
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      'Unable to reach the backend. Check that it is running and the URL is correct.',
    );
  } finally {
    clearTimeout(timeout);
  }
}

export async function postJson<T extends ApiResponse>(
  path: '/status' | '/location',
  body: StatusPayload | LocationPayload,
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