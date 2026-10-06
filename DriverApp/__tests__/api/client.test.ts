import AsyncStorage from '@react-native-async-storage/async-storage';
import { createDriverToken } from '../../src/api/client';

const mockedStorage = AsyncStorage as jest.Mocked<typeof AsyncStorage>;
const fetchMock = jest.fn();

describe('createDriverToken', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedStorage.getItem.mockResolvedValue('http://localhost:8000');
    global.fetch = fetchMock;
  });

  it('creates a driver token through the existing admin endpoint', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 'driver-id',
        name: 'Amina',
        token: 'one-time-driver-token',
      }),
    });

    const token = await createDriverToken({
      adminKey: 'admin-secret',
      name: 'Amina',
      phone: '+15550100',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/admin/drivers',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-admin-key': 'admin-secret',
        },
        body: JSON.stringify({ name: 'Amina', phone: '+15550100' }),
      }),
    );
    expect(token).toBe('one-time-driver-token');
  });

  it('rejects an unsuccessful driver creation response', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid admin key' }),
    });

    await expect(
      createDriverToken({
        adminKey: 'wrong-key',
        name: 'Amina',
        phone: '+15550100',
      }),
    ).rejects.toThrow('Invalid admin key');
  });
});
