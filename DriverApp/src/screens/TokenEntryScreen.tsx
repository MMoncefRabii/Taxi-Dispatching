import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Keyboard,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { createDriverToken } from '../api/client';

interface Props {
  onTokenSaved: (token: string) => void;
}

export function TokenEntryScreen({ onTokenSaved }: Props) {
  const [adminKey, setAdminKey] = useState('');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [saving, setSaving] = useState(false);

  const saveToken = async () => {
    const normalizedAdminKey = adminKey.trim();
    const normalizedName = name.trim();
    const normalizedPhone = phone.trim();
    if (!normalizedAdminKey || !normalizedName || !normalizedPhone || saving) {
      return;
    }

    setSaving(true);
    try {
      const token = await createDriverToken({
        adminKey: normalizedAdminKey,
        name: normalizedName,
        phone: normalizedPhone,
      });
      await AsyncStorage.setItem('driver_token', token);
      Keyboard.dismiss();
      onTokenSaved(token);
    } catch (error) {
      console.warn('Unable to create driver token:', error);
      Alert.alert(
        'Unable to get driver token',
        error instanceof Error ? error.message : 'Please try again.',
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.content}>
        <View style={styles.mark}>
          <Text style={styles.markText}>D</Text>
        </View>
        <Text style={styles.eyebrow}>TEMPORARY DRIVER ACCESS</Text>
        <Text style={styles.title}>Request a driver token</Text>
        <Text style={styles.description}>
          The admin dashboard creates the driver account. This mobile flow receives the
          one-time token returned by the existing admin endpoint.
        </Text>
        <TextInput
          accessibilityLabel="Admin key"
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          onChangeText={setAdminKey}
          placeholder="Admin key"
          placeholderTextColor="#7c8581"
          returnKeyType="next"
          style={styles.input}
          value={adminKey}
        />
        <TextInput
          accessibilityLabel="Driver name"
          autoCapitalize="words"
          autoCorrect={false}
          onChangeText={setName}
          placeholder="Driver name"
          placeholderTextColor="#7c8581"
          returnKeyType="next"
          style={styles.input}
          value={name}
        />
        <TextInput
          accessibilityLabel="Driver phone"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="phone-pad"
          onChangeText={setPhone}
          placeholder="Driver phone"
          placeholderTextColor="#7c8581"
          returnKeyType="done"
          style={styles.input}
          value={phone}
        />
        <TouchableOpacity
          accessibilityRole="button"
          disabled={!adminKey.trim() || !name.trim() || !phone.trim() || saving}
          onPress={saveToken}
          style={[
            styles.button,
            (!adminKey.trim() || !name.trim() || !phone.trim() || saving) &&
              styles.disabled,
          ]}>
          {saving ? (
            <ActivityIndicator color="#ffffff" />
          ) : (
            <Text style={styles.buttonText}>Request token</Text>
          )}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: '#f4f6f3' },
  content: { flex: 1, justifyContent: 'center', paddingHorizontal: 28 },
  mark: {
    width: 52,
    height: 52,
    borderRadius: 16,
    backgroundColor: '#dce9e0',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 32,
  },
  markText: { color: '#215b3c', fontSize: 26, fontWeight: '700' },
  eyebrow: { color: '#427758', fontSize: 12, fontWeight: '700', letterSpacing: 1 },
  title: { color: '#1c2822', fontSize: 30, fontWeight: '700', marginTop: 10 },
  description: {
    color: '#65716a',
    fontSize: 16,
    lineHeight: 23,
    marginTop: 10,
    marginBottom: 8,
  },
  input: {
    minHeight: 52,
    maxHeight: 110,
    borderWidth: 1,
    borderColor: '#cbd4cd',
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginTop: 12,
    color: '#1c2822',
    backgroundColor: '#ffffff',
    fontSize: 15,
  },
  button: {
    minHeight: 54,
    borderRadius: 10,
    backgroundColor: '#215b3c',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 14,
  },
  buttonText: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
  disabled: { opacity: 0.48 },
});