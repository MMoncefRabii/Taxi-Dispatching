import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React, { useEffect, useState } from 'react';
import { Alert, StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { setUnauthorizedHandler } from './src/api/client';
import { locationQueue } from './src/location/queue';
import { stopLocationTracking } from './src/location/tracker';
import { TokenEntryScreen } from './src/screens/TokenEntryScreen';
import { MainScreen } from './src/screens/MainScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';

export type RootStackParamList = {
  TokenEntry: undefined;
  Main: undefined;
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

function AppNavigation() {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    AsyncStorage.getItem('driver_token')
      .then(setToken)
      .catch(error => console.warn('Unable to load driver token:', error))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(async () => {
      let cleanupIssue = false;
      try {
        await stopLocationTracking();
      } catch {
        cleanupIssue = true;
      }
      try {
        await locationQueue.clear();
      } catch {
        cleanupIssue = true;
      }
      try {
        await AsyncStorage.setItem('driver_online', 'false');
      } catch {
        cleanupIssue = true;
      }
      try {
        await AsyncStorage.removeItem('driver_token');
      } catch {
        cleanupIssue = true;
      }
      Alert.alert(
        'Invalid driver token',
        cleanupIssue
          ? 'Your token was rejected. Location data could not be fully cleared; it will be cleared before another token is saved.'
          : 'Your token was rejected. Please check it with your admin and enter it again.',
      );
      setToken(null);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const logout = async () => {
    let cleanupIssue = false;
    try {
      await stopLocationTracking();
    } catch {
      cleanupIssue = true;
    }
    try {
      await locationQueue.clear();
    } catch {
      cleanupIssue = true;
    }
    try {
      await AsyncStorage.setItem('driver_online', 'false');
    } catch {
      cleanupIssue = true;
    }
    try {
      await AsyncStorage.removeItem('driver_token');
    } catch {
      cleanupIssue = true;
    }
    if (cleanupIssue) {
      Alert.alert(
        'Logout cleanup incomplete',
        'Tracking or saved locations could not be fully cleared. They will be cleared before another token is saved.',
      );
    }
    setToken(null);
  };

  if (loading) {
    return null;
  }

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {token ? (
          <>
            <Stack.Screen name="Main">
              {({ navigation }) => (
                <MainScreen onOpenSettings={() => navigation.navigate('Settings')} />
              )}
            </Stack.Screen>
            <Stack.Screen name="Settings">
              {({ navigation }) => (
                <SettingsScreen
                  onBack={() => navigation.goBack()}
                  onLogout={logout}
                />
              )}
            </Stack.Screen>
          </>
        ) : (
          <Stack.Screen name="TokenEntry">
            {() => <TokenEntryScreen onTokenSaved={setToken} />}
          </Stack.Screen>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar barStyle="dark-content" />
      <AppNavigation />
    </SafeAreaProvider>
  );
}