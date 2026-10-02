import React, { useEffect, useState } from 'react';
import {
  Alert,
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
import { startLocationTracking, stopLocationTracking } from '../location/tracker';

interface Props {
  onOpenSettings: () => void;
}

async function requestLocationPermission(): Promise<boolean> {
  if (Platform.OS === 'ios') {
    return (await Geolocation.requestAuthorization('whenInUse')) === 'granted';
  }
  if (Platform.OS !== 'android') {
    return true;
  }

  const results = await PermissionsAndroid.requestMultiple([
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    PermissionsAndroid.PERMISSIONS.ACCESS_COARSE_LOCATION,
  ]);
  return (
    results[PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION] ===
    PermissionsAndroid.RESULTS.GRANTED
  );
}

function formatElapsed(seconds: number): string {
  return seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;
}

export function MainScreen({ onOpenSettings }: Props) {
  const [online, setOnline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastSent, setLastSent] = useState<LocationPayload | null>(null);
  const [lastSentAt, setLastSentAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [syncIssue, setSyncIssue] = useState(false);

  useEffect(() => {
    if (lastSentAt === null) {
      return;
    }
    const timer = setInterval(
      () => setElapsedSeconds(Math.floor((Date.now() - lastSentAt) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [lastSentAt]);

  useEffect(() => () => stopLocationTracking(), []);

  const receiveLocation = (location: LocationPayload) => {
    setLastSent(location);
    setLastSentAt(
      location.recorded_at ? location.recorded_at * 1000 : Date.now(),
    );
    setElapsedSeconds(0);
  };

  const changeStatus = async (nextOnline: boolean) => {
    if (busy) {
      return;
    }
    setBusy(true);
    try {
      if (nextOnline) {
        const permissionGranted = await requestLocationPermission();
        if (!permissionGranted) {
          Alert.alert(
            'Location permission needed',
            'Allow precise location access in system settings before going online.',
          );
          return;
        }
      }

      await postJson<ApiResponse>('/status', { online: nextOnline });
      if (nextOnline) {
        setOnline(true);
        setSyncIssue(false);
        startLocationTracking(receiveLocation, setSyncIssue);
      } else {
        stopLocationTracking();
        setOnline(false);
        setSyncIssue(false);
      }
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        console.warn('Unable to change driver status:', error);
        Alert.alert(
          'Status not updated',
          error instanceof Error
            ? error.message
            : 'Check your connection and try again.',
        );
      }
    } finally {
      setBusy(false);
    }
  };

  const coordinates = lastSent
    ? `${lastSent.lat.toFixed(5)}, ${lastSent.lng.toFixed(5)}`
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
          <Text style={styles.settingsIcon}>⚙</Text>
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
            onValueChange={value => changeStatus(value)}
            trackColor={{ false: '#cbd2ce', true: '#74a987' }}
            thumbColor={online ? '#215b3c' : '#f9fbf9'}
            value={online}
          />
        </View>
        <View style={styles.divider} />
        <View style={styles.stateRow}>
          <View style={[styles.dot, online ? styles.onlineDot : styles.offlineDot]} />
          <Text style={styles.stateDescription}>
            {online
              ? lastSentAt === null
                ? 'Online — waiting for location'
                : 'Online — sending location'
              : 'Offline'}
          </Text>
        </View>
        {syncIssue && online ? (
          <Text style={styles.syncIssue}>Sync issue · checking connection</Text>
        ) : null}
      </View>

      <View style={styles.locationSection}>
        <Text style={styles.sectionLabel}>LOCATION CHECK-IN</Text>
        <View style={styles.locationRow}>
          <View style={styles.locationGlyph}>
            <Text style={styles.pin}>⌖</Text>
          </View>
          <View style={styles.locationDetails}>
            <Text style={styles.coordinates}>{coordinates}</Text>
            <Text style={styles.lastSent}>
              Last sent: {lastSentAt === null ? '—' : formatElapsed(elapsedSeconds)}
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
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: '#e5ebe6',
    alignItems: 'center',
    justifyContent: 'center',
  },
  settingsIcon: { color: '#354c3f', fontSize: 23 },
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
  stateRow: { flexDirection: 'row', alignItems: 'center' },
  dot: { width: 9, height: 9, borderRadius: 5, marginRight: 9 },
  onlineDot: { backgroundColor: '#2e8750' },
  offlineDot: { backgroundColor: '#89918c' },
  stateDescription: { color: '#4f5d55', fontSize: 14 },
  syncIssue: { color: '#9a6424', fontSize: 13, marginTop: 12 },
  locationSection: { marginTop: 36 },
  sectionLabel: { color: '#597268', fontSize: 12, fontWeight: '700', letterSpacing: 0.8 },
  locationRow: { flexDirection: 'row', alignItems: 'center', marginTop: 16 },
  locationGlyph: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: '#e5ebe6',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 13,
  },
  pin: { color: '#35694a', fontSize: 25 },
  locationDetails: { flex: 1 },
  coordinates: { color: '#26332b', fontSize: 15, fontWeight: '600' },
  lastSent: { color: '#718078', fontSize: 13, marginTop: 5 },
  pending: { color: '#718078', textAlign: 'center', marginTop: 26, fontSize: 13 },
});