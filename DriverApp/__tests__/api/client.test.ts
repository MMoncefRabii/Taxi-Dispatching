import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  ApiError,
  postJson,
  setUnauthorizedHandler,
} from '../../src/api/client';

const mockedStorage = AsyncStorage as jest.Mocked<typeof AsyncStorage>;
const fetchMock = jest.fn();

describe('postJson', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedStorage.getItem.mockImplementation(async key =>
      key === 'driver_token' ? 'driver-token' : 'http://localhost:8000',
    );
    global.fetch = fetchMock;
    setUnauthorizedHandler(null);
  });

  afterEach(() => setUnauthorizedHandler(null));

  it('sends the saved driver token to the requested driver endpoint', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });

    const result = await postJson('/status', { online: true });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/status',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-token': 'driver-token',
        },
        body: JSON.stringify({ online: true }),
      }),
    );
    expect(result).toEqual({ ok: true });
  });

  it('runs the unauthorized handler and rejects a 401 response', async () => {
    const unauthorizedHandler = jest.fn();
    setUnauthorizedHandler(unauthorizedHandler);
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
    });

    await expect(postJson('/status', { online: false })).rejects.toEqual(
      new ApiError('Session expired.', 401),
    );
    expect(unauthorizedHandler).toHaveBeenCalledTimes(1);
  });
});
