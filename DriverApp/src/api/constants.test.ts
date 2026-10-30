import {
  DEBUG_BASE_URL,
  RELEASE_BASE_URL_PLACEHOLDER,
  validateBackendUrl,
} from './constants';

describe('validateBackendUrl', () => {
  it('accepts and normalizes the debug emulator URL', () => {
    expect(validateBackendUrl(`${DEBUG_BASE_URL}/`, true)).toBe(DEBUG_BASE_URL);
  });

  it('accepts an HTTPS production origin', () => {
    expect(validateBackendUrl('https://driver-api.invalid', false)).toBe(
      'https://driver-api.invalid',
    );
  });

  it.each([
    ['', 'Backend URL is required.'],
    ['not a URL', 'Enter a valid backend URL.'],
    [
      'http://driver-api.invalid',
      'Backend URL must use HTTPS in release builds.',
    ],
    [
      RELEASE_BASE_URL_PLACEHOLDER,
      'Replace the placeholder with your production API domain.',
    ],
    [
      'https://driver-api.invalid/v1',
      'Backend URL must be an origin only, without credentials, path, query, or fragment.',
    ],
  ])('rejects invalid URL %s', (value, message) => {
    expect(() => validateBackendUrl(value, false)).toThrow(message);
  });
});
