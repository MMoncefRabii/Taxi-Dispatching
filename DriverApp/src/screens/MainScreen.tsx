import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  AppState,
  Linking,
  PermissionsAndroid,
  Platform,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import Geolocation from 'react-native-geolocation-service';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ApiError, ApiResponse, LocationPayload, postJson } from '../api/client';
import {
  createEmptyQueue,
  locationQueue,
} from '../location/queue';
import type { QueueState } from '../location/queue';
import {
  startLocationTracking,
  stopLocationTracking,
} from '../location/tracker';

interface Props {
  onOpenSettings: () => void;
}

const DRIVER_ONLINE_STORAGE_KEY = 'driver_online';

async function checkTrackingPermissions(): Promise<boolean> {
  if (Platform.OS !== 'android') {
    return true;
  }
  const apiLevel = Number(Platform.Version);
  const foregroundGranted = await PermissionsAndroid.check(
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
  );
  if (!foregroundGranted) {
    return false;
  }
  if (
    apiLevel >= 29 &&
    !(await PermissionsAndroid.check(
      PermissionsAndroid.PERMISSIONS.ACCESS_BACKGROUND_LOCATION,
    ))
  ) {
    return false;
  }
  if (
    apiLevel >= 33 &&
    !(await PermissionsAndroid.check(
      PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS,
    ))
  ) {
    return false;
  }
  return true;
}

async function requestTrackingPermissions(): Promise<string | null> {
  if (Platform.OS === 'ios') {
    return (await Geolocation.requestAuthorization('whenInUse')) === 'granted'
      ? null
      : 'Allow location access in Settings before going online.';
  }
  if (Platform.OS !== 'android') {
    return null;
  }

  const foreground = await PermissionsAndroid.requestMultiple([
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    PermissionsAndroid.PERMISSIONS.ACCESS_COARSE_LOCATION,
  ]);
  if (
    foreground[PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION] !==
    PermissionsAndroid.RESULTS.GRANTED
  ) {
    return 'Precise foreground location permission is required to go online.';
  }

  const apiLevel = Number(Platform.Version);
  if (apiLevel >= 30) {
    const backgroundGranted = await PermissionsAndroid.check(
      PermissionsAndroid.PERMISSIONS.ACCESS_BACKGROUND_LOCATION,
    );
    if (!backgroundGranted) {
      return 'Open app Settings > Permissions > Location > Allow all the time, then return and try again so tracking can continue while the screen is locked.';
    }
  } else if (apiLevel >= 29) {
    const background = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.ACCESS_BACKGROUND_LOCATION,
    );
    if (background !== PermissionsAndroid.RESULTS.GRANTED) {
      return 'Background location permission is required to keep tracking while the screen is locked.';
    }
  }

  if (
    apiLevel >= 33 &&
    (await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS,
    )) !== PermissionsAndroid.RESULTS.GRANTED
  ) {
    return 'Allow notifications in app Settings so Android can show the active location-tracking service.';
  }
  return null;
}

function formatTimestamp(timestamp: number | null): string {
  return timestamp === null ? 'Never' : new Date(timestamp).toLocaleString();
}

export function MainScreen({ onOpenSettings }: Props) {
  const [online, setOnline] = useState(false);
  const [busy, setBusy] = useState(true);
  const [lastLocation, setLastLocation] = useState<LocationPayload | null>(null);
  const [queueState, setQueueState] = useState<QueueState>(createEmptyQueue);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [permissionIssue, setPermissionIssue] = useState<string | null>(null);

  const receiveLocation = useCallback((location: LocationPayload) => {
    setLastLocation(location);
  }, []);
  const receiveQueueState = useCallback((state: QueueState) => {
    setQueueState(state);
    setSyncError(state.error);
  }, []);
  const receiveSyncError = useCallback((message: string | null) => {
    setSyncError(message);
  }, []);

  const trackerCallbacks = useMemo(
    () => ({
      onLocation: receiveLocation,
      onQueueState: receiveQueueState,
      onError: receiveSyncError,
    }),
    [receiveLocation, receiveQueueState, receiveSyncError],
  );

  const restoreTracking = useCallback(async () => {
    setBusy(true);
    try {
      const [savedOnline, savedQueue] = await Promise.all([
        AsyncStorage.getItem(DRIVER_ONLINE_STORAGE_KEY),
        locationQueue.getState(),
      ]);
      setQueueState(savedQueue);
      setSyncError(savedQueue.error);
      if (savedOnline !== 'true') {
        await stopLocationTracking();
        return;
      }

      if (await checkTrackingPermissions()) {
        try {
          await startLocationTracking(trackerCallbacks);
          setOnline(true);
        } catch {
          setOnline(false);
          setPermissionIssue(
            'Tracking could not be resumed. Check permissions and try going online again.',
          );
          try {
            await stopLocationTracking();
          } catch {
            setSyncError('Unable to confirm that background tracking stopped.');
          }
          await AsyncStorage.setItem(DRIVER_ONLINE_STORAGE_KEY, 'false');
          try {
            await postJson<ApiResponse>('/status', { online: false });
          } catch (error) {
            if (!(error instanceof ApiError && error.status === 401)) {
              setSyncError('Tracking is offline, but server availability could not be updated.');
            }
          }
        }
        return;
      }

      await stopLocationTracking();
      await AsyncStorage.setItem(DRIVER_ONLINE_STORAGE_KEY, 'false');
      setOnline(false);
      setPermissionIssue(
        'Tracking is offline because required location or notification permissions are not enabled.',
      );
      try {
        await postJson<ApiResponse>('/status', { online: false });
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 401)) {
          setSyncError('Could not update availability while permissions were missing.');
        }
      }
    } catch {
      setSyncError('Unable to restore the saved tracking state or location queue.');
    } finally {
      setBusy(false);
    }
  }, [trackerCallbacks]);

  useEffect(() => {
    restoreTracking().catch(() => {
      setSyncError('Unable to restore tracking state.');
    });
  }, [restoreTracking]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') {
        locationQueue
          .getState()
          .then(receiveQueueState)
          .catch(() =>
            setSyncError('Unable to read the saved location queue.'),
          );
      }
    });
    return () => subscription.remove();
  }, [receiveQueueState]);

  const explainPermissionIssue = (message: string) => {
    setPermissionIssue(message);
    Alert.alert('Permission needed to go online', message, [
      { text: 'Not now', style: 'cancel' },
      {
        text: 'Open settings',
        onPress: openPermissionSettings,
      },
    ]);
  };

  const changeStatus = async (nextOnline: boolean) => {
    if (busy) {
      return;
    }
    setBusy(true);
    setPermissionIssue(null);
    try {
      if (nextOnline) {
        const permissionError = await requestTrackingPermissions();
        if (permissionError) {
          explainPermissionIssue(permissionError);
          return;
        }
        await postJson<ApiResponse>('/status', { online: true });
        await AsyncStorage.setItem(DRIVER_ONLINE_STORAGE_KEY, 'true');
        await startLocationTracking(trackerCallbacks);
        setOnline(true);
        setSyncError(null);
      } else {
        await stopLocationTracking();
        await AsyncStorage.setItem(DRIVER_ONLINE_STORAGE_KEY, 'false');
        setOnline(false);
        try {
          await postJson<ApiResponse>('/status', { online: false });
          setSyncError(null);
        } catch (error) {
          if (error instanceof ApiError && error.status === 401) {
            return;
          }
          setSyncError(
            'Tracking stopped, but server availability could not be updated.',
          );
          Alert.alert(
            'Availability not updated',
            'Tracking stopped on this device, but the server did not confirm the offline status.',
          );
        }
      }
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        const message =
          error instanceof Error
            ? error.message
            : 'Check your connection and try again.';
        setSyncError(message);
        Alert.alert('Status not updated', message);
        if (nextOnline) {
          setOnline(false);
          try {
            await stopLocationTracking();
          } catch {
            setSyncError('Unable to confirm that background tracking stopped.');
          }
          try {
            await AsyncStorage.setItem(DRIVER_ONLINE_STORAGE_KEY, 'false');
          } catch {
            setSyncError('Unable to save the offline state on this device.');
          }
          try {
            await postJson<ApiResponse>('/status', { online: false });
          } catch {
            setSyncError('Tracking did not start; availability may need a retry.');
          }
        } else {
          setOnline(false);
          try {
            await AsyncStorage.setItem(DRIVER_ONLINE_STORAGE_KEY, 'false');
          } catch {
            setSyncError('Unable to save the offline state on this device.');
          }
          try {
            await postJson<ApiResponse>('/status', { online: false });
          } catch (statusError) {
            if (!(statusError instanceof ApiError && statusError.status === 401)) {
              setSyncError('Tracking could not be stopped cleanly.');
            }
          }
        }
      }
    } finally {
      setBusy(false);
    }
  };

  const openPermissionSettings = () =>
    Linking.openSettings().catch(() => {
      setSyncError('Unable to open Android app settings.');
    });

  const coordinates = lastLocation
    ? `${lastLocation.lat.toFixed(5)}, ${lastLocation.lng.toFixed(5)}`
    : 'Waiting for first location';

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>DRIVER</Text>
          <Text style={styles.title}>Your shift</Text>
        </View>
        <TouchableOpacity
          accessibilityLabel="Settings"
          accessibilityRole="button"
          onPress={onOpenSettings}
          style={styles.settingsButton}>
          <Text style={styles.settingsIcon}>Settings</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.statusPanel}>
        <View style={styles.statusTop}>
          <View>
            <Text style={styles.statusLabel}>Availability</Text>
            <Text style={styles.stateText}>{online ? 'Online' : 'Offline'}</Text>
          </View>
          <Switch
            accessibilityLabel={online ? 'Go offline' : 'Go online'}
            disabled={busy}
            onValueChange={value => {
              changeStatus(value).catch(() =>
                setSyncError('Unable to update availability.'),
              );
            }}
            trackColor={{ false: '#cbd2ce', true: '#74a987' }}
            thumbColor={online ? '#215b3c' : '#f9fbf9'}
            value={online}
          />
        </View>
        <View style={styles.divider} />
        <Text style={styles.stateDescription}>
          {online ? 'Location tracking is active.' : 'Location tracking is stopped.'}
        </Text>
        <Text style={styles.queueStatus}>
          Saved locations waiting to sync: {queueState.entries.length}
        </Text>
        <Text style={styles.queueStatus}>
          Dropped or rejected locations: {queueState.droppedCount}
        </Text>
        <Text style={styles.queueStatus}>
          Last successful sync: {formatTimestamp(queueState.lastSuccessfulSyncAt)}
        </Text>
        {syncError ? <Text style={styles.syncIssue}>{syncError}</Text> : null}
        {permissionIssue && !online ? (
          <View>
            <Text style={styles.permissionIssue}>{permissionIssue}</Text>
            <TouchableOpacity
              accessibilityRole="button"
              onPress={openPermissionSettings}
              style={styles.permissionButton}>
              <Text style={styles.permissionButtonText}>Open app settings</Text>
            </TouchableOpacity>
          </View>
        ) : null}
      </View>

      <View style={styles.locationSection}>
        <Text style={styles.sectionLabel}>LOCATION CHECK-IN</Text>
        <View style={styles.locationRow}>
          <View style={styles.locationGlyph}>
            <Text style={styles.pin}>Location</Text>
          </View>
          <View style={styles.locationDetails}>
            <Text style={styles.coordinates}>{coordinates}</Text>
            <Text style={styles.lastSent}>
              Last fix: {lastLocation?.recorded_at
                ? formatTimestamp(lastLocation.recorded_at * 1000)
                : '—'}
            </Text>
          </View>
        </View>
      </View>

      {busy ? <Text style={styles.pending}>Updating availability…</Text> : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#f4f6f3', paddingHorizontal: 24 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 20,
    paddingBottom: 30,
  },
  eyebrow: { color: '#597268', fontSize: 12, fontWeight: '700', letterSpacing: 1 },
  title: { color: '#1c2822', fontSize: 29, fontWeight: '700', marginTop: 5 },
  settingsButton: {
    minWidth: 44,
    height: 44,
    paddingHorizontal: 12,
    borderRadius: 12,
    backgroundColor: '#e5ebe6',
    alignItems: 'center',
    justifyContent: 'center',
  },
  settingsIcon: { color: '#354c3f', fontSize: 14, fontWeight: '600' },
  statusPanel: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#e1e7e2',
    borderRadius: 12,
    padding: 20,
  },
  statusTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  statusLabel: { color: '#66736b', fontSize: 14 },
  stateText: { color: '#1c2822', fontSize: 24, fontWeight: '700', marginTop: 5 },
  divider: { height: 1, backgroundColor: '#e6ebe7', marginVertical: 17 },
  stateDescription: { color: '#4f5d55', fontSize: 14 },
  queueStatus: { color: '#4f5d55', fontSize: 13, marginTop: 8 },
  syncIssue: { color: '#9a6424', fontSize: 13, marginTop: 12 },
  permissionIssue: { color: '#9a6424', fontSize: 13, lineHeight: 19, marginTop: 12 },
  permissionButton: {
    minHeight: 42,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#9a6424',
    borderRadius: 9,
    marginTop: 10,
  },
  permissionButtonText: { color: '#81531f', fontSize: 14, fontWeight: '600' },
  locationSection: { marginTop: 36 },
  sectionLabel: { color: '#597268', fontSize: 12, fontWeight: '700', letterSpacing: 0.8 },
  locationRow: { flexDirection: 'row', alignItems: 'center', marginTop: 16 },
  locationGlyph: {
    width: 66,
    height: 44,
    borderRadius: 12,
    backgroundColor: '#e5ebe6',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 13,
  },
  pin: { color: '#35694a', fontSize: 12, fontWeight: '600' },
  locationDetails: { flex: 1 },
  coordinates: { color: '#26332b', fontSize: 15, fontWeight: '600' },
  lastSent: { color: '#718078', fontSize: 13, marginTop: 5 },
  pending: { color: '#718078', textAlign: 'center', marginTop: 26, fontSize: 13 },
});
