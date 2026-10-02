import AsyncStorage from '@react-native-async-storage/async-storage';

export const BASE_URL = 'http://10.0.2.2:8000';
export const BACKEND_URL_KEY = 'backend_url';

export async function getBackendUrl(): Promise<string> {
  return (await AsyncStorage.getItem(BACKEND_URL_KEY)) || BASE_URL;
}

export async function saveBackendUrl(url: string): Promise<void> {
  await AsyncStorage.setItem(BACKEND_URL_KEY, url.trim().replace(/\/+$/, ''));
}