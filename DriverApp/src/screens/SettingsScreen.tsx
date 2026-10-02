import React, { useEffect, useState } from 'react';
import {
  Alert,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { getBackendUrl, saveBackendUrl } from '../api/constants';

interface Props {
  onBack: () => void;
  onLogout: () => Promise<void>;
}

export function SettingsScreen({ onBack, onLogout }: Props) {
  const [backendUrl, setBackendUrl] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getBackendUrl()
      .then(setBackendUrl)
      .catch(error => console.warn('Unable to load backend URL:', error));
  }, []);

  const saveUrl = async () => {
    const value = backendUrl.trim();
    if (!value || saving) {
      return;
    }
    setSaving(true);
    try {
      await saveBackendUrl(value);
      setBackendUrl(value.replace(/\/+$/, ''));
      Alert.alert('Saved', 'Backend URL updated.');
    } catch (error) {
      console.warn('Unable to save backend URL:', error);
      Alert.alert('Unable to save URL', 'Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const confirmLogout = () => {
    Alert.alert('Log out?', 'Your saved driver token will be removed.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Log out', style: 'destructive', onPress: onLogout },
    ]);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.header}>
        <TouchableOpacity accessibilityRole="button" onPress={onBack}>
          <Text style={styles.back}>‹  Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Settings</Text>
      </View>

      <Text style={styles.label}>BACKEND URL</Text>
      <TextInput
        accessibilityLabel="Backend URL"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        onChangeText={setBackendUrl}
        placeholder="http://10.0.2.2:8000"
        placeholderTextColor="#7c8581"
        style={styles.input}
        value={backendUrl}
      />
      <TouchableOpacity
        accessibilityRole="button"
        disabled={!backendUrl.trim() || saving}
        onPress={saveUrl}
        style={[styles.button, (!backendUrl.trim() || saving) && styles.disabled]}>
        <Text style={styles.buttonText}>{saving ? 'Saving…' : 'Save URL'}</Text>
      </TouchableOpacity>

      <View style={styles.separator} />
      <TouchableOpacity
        accessibilityRole="button"
        onPress={confirmLogout}
        style={styles.logoutButton}>
        <Text style={styles.logoutText}>Log out</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#f4f6f3', paddingHorizontal: 24 },
  header: { paddingTop: 18, paddingBottom: 34 },
  back: { color: '#35694a', fontSize: 15, fontWeight: '600' },
  title: { color: '#1c2822', fontSize: 29, fontWeight: '700', marginTop: 18 },
  label: { color: '#597268', fontSize: 12, fontWeight: '700', letterSpacing: 0.8 },
  input: {
    height: 54,
    borderWidth: 1,
    borderColor: '#cbd4cd',
    borderRadius: 10,
    paddingHorizontal: 14,
    color: '#1c2822',
    backgroundColor: '#ffffff',
    marginTop: 11,
    fontSize: 15,
  },
  button: {
    height: 50,
    borderRadius: 10,
    backgroundColor: '#215b3c',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 12,
  },
  buttonText: { color: '#ffffff', fontWeight: '700', fontSize: 15 },
  disabled: { opacity: 0.48 },
  separator: { height: 1, backgroundColor: '#dce3dd', marginVertical: 30 },
  logoutButton: {
    height: 50,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#bf635d',
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoutText: { color: '#a4443d', fontSize: 15, fontWeight: '700' },
});