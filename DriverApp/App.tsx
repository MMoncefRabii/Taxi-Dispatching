import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React, { useEffect, useState } from 'react';
import { Alert, StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { setUnauthorizedHandler } from './src/api/client';
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
      await AsyncStorage.removeItem('driver_token');
      Alert.alert('Session expired', 'Please re-enter your token.');
      setToken(null);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

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
                  onLogout={async () => {
                    await AsyncStorage.removeItem('driver_token');
                    setToken(null);
                  }}
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