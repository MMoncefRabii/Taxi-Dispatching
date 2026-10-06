import AsyncStorage from '@react-native-async-storage/async-storage';
import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import { TokenEntryScreen } from '../../src/screens/TokenEntryScreen';

const mockedStorage = AsyncStorage as jest.Mocked<typeof AsyncStorage>;

describe('TokenEntryScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('trims and stores a pasted token before notifying the app', async () => {
    const onTokenSaved = jest.fn();
    let renderer: ReactTestRenderer.ReactTestRenderer;

    await ReactTestRenderer.act(() => {
      renderer = ReactTestRenderer.create(
        <TokenEntryScreen onTokenSaved={onTokenSaved} />,
      );
    });

    const tokenInput = renderer!.root.findByProps({
      accessibilityLabel: 'Driver token',
    });

    await ReactTestRenderer.act(() => tokenInput.props.onChangeText('  driver-token  '));
    const saveButton = renderer!.root.findByProps({
      accessibilityRole: 'button',
    });
    await ReactTestRenderer.act(() => saveButton.props.onPress());

    expect(mockedStorage.setItem).toHaveBeenCalledWith(
      'driver_token',
      'driver-token',
    );
    expect(onTokenSaved).toHaveBeenCalledWith('driver-token');
  });

  it('does not save an empty or whitespace-only token', async () => {
    const onTokenSaved = jest.fn();
    let renderer: ReactTestRenderer.ReactTestRenderer;

    await ReactTestRenderer.act(() => {
      renderer = ReactTestRenderer.create(
        <TokenEntryScreen onTokenSaved={onTokenSaved} />,
      );
    });

    const tokenInput = renderer!.root.findByProps({
      accessibilityLabel: 'Driver token',
    });
    await ReactTestRenderer.act(() => tokenInput.props.onChangeText('   '));
    const saveButton = renderer!.root.findByProps({
      accessibilityRole: 'button',
    });
    await ReactTestRenderer.act(() => saveButton.props.onPress());

    expect(mockedStorage.setItem).not.toHaveBeenCalled();
    expect(onTokenSaved).not.toHaveBeenCalled();
  });
});
