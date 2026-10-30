import AsyncStorage from '@react-native-async-storage/async-storage';
import { NativeModules } from 'react-native';

export const DEBUG_BASE_URL = 'http://10.0.2.2:8000';
export const RELEASE_BASE_URL_PLACEHOLDER = 'https://REPLACE_WITH_API_DOMAIN';
export const BACKEND_URL_KEY = 'backend_url';

const nativeBaseUrl: unknown = NativeModules.DriverAppConfig?.apiBaseUrl;

export const BASE_URL =
  typeof nativeBaseUrl === 'string'
    ? nativeBaseUrl
    : __DEV__
      ? DEBUG_BASE_URL
      : RELEASE_BASE_URL_PLACEHOLDER;

export function validateBackendUrl(
  value: string,
  allowHttp = __DEV__,
): string {
  const trimmedValue = value.trim();
  if (!trimmedValue) {
    throw new Error('Backend URL is required.');
  }

  let url: URL;
  try {
    url = new URL(trimmedValue);
  } catch {
    throw new Error('Enter a valid backend URL.');
  }

  if (
    url.protocol !== 'https:' &&
    !(allowHttp && url.protocol === 'http:')
  ) {
    throw new Error('Backend URL must use HTTPS in release builds.');
  }
  if (
    url.hostname === 'replace_with_api_domain' ||
    url.hostname.endsWith('.example.invalid') ||
    url.hostname.includes('<') ||
    url.hostname.includes('>')
  ) {
    throw new Error('Replace the placeholder with your production API domain.');
  }
  if (
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash
  ) {
    throw new Error(
      'Backend URL must be an origin only, without credentials, path, query, or fragment.',
    );
  }

  return url.origin;
}

export async function getBackendUrl(): Promise<string> {
  const savedUrl = await AsyncStorage.getItem(BACKEND_URL_KEY);
  return validateBackendUrl(savedUrl || BASE_URL);
}

export async function saveBackendUrl(url: string): Promise<void> {
  await AsyncStorage.setItem(BACKEND_URL_KEY, validateBackendUrl(url));
}