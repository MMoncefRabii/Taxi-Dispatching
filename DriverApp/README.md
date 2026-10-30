The Fleet Tracker driver app is the mobile frontend, built with React Native and TypeScript. `src/` contains its screens, API client, and location tracking code; `android/` and `ios/` contain the native platform projects. It communicates with the separate Python FastAPI backend. Mobile UI changes belong here; backend changes are needed only when the API contract or server behavior changes. See the repository root README for backend and database setup.

# Getting Started

> **Note**: Make sure you have completed the [Set Up Your Environment](https://reactnative.dev/docs/set-up-your-environment) guide before proceeding.

## Step 1: Start Metro

First, you will need to run **Metro**, the JavaScript build tool for React Native.

To start the Metro dev server, run the following command from the root of your React Native project:

```sh
# Using npm
npm start

# OR using Yarn
yarn start
```

## Step 2: Build and run your app

With Metro running, open a new terminal window/pane from the root of your React Native project, and use one of the following commands to build and run your Android or iOS app:

### Android

```sh
# Using npm
npm run android

# OR using Yarn
yarn android
```

### iOS

For iOS, remember to install CocoaPods dependencies (this only needs to be run on first clone or after updating native deps).

The first time you create a new project, run the Ruby bundler to install CocoaPods itself:

```sh
bundle install
```

Then, and every time you update your native dependencies, run:

```sh
bundle exec pod install
```

For more information, please visit [CocoaPods Getting Started guide](https://guides.cocoapods.org/using/getting-started.html).

```sh
# Using npm
npm run ios

# OR using Yarn
yarn ios
```

If everything is set up correctly, you should see your new app running in the Android Emulator, iOS Simulator, or your connected device.

This is one way to run your app — you can also build it directly from Android Studio or Xcode.

## Step 3: Modify your app

Now that you have successfully run the app, let's make changes!

Open `App.tsx` in your text editor of choice and make some changes. When you save, your app will automatically update and reflect these changes — this is powered by [Fast Refresh](https://reactnative.dev/docs/fast-refresh).

When you want to forcefully reload, for example to reset the state of your app, you can perform a full reload:

- **Android**: Press the <kbd>R</kbd> key twice or select **"Reload"** from the **Dev Menu**, accessed via <kbd>Ctrl</kbd> + <kbd>M</kbd> (Windows/Linux) or <kbd>Cmd ⌘</kbd> + <kbd>M</kbd> (macOS).
- **iOS**: Press <kbd>R</kbd> in iOS Simulator.

## Congratulations! :tada:

You've successfully run and modified your React Native App. :partying_face:

### Now what?

- If you want to add this new React Native code to an existing application, check out the [Integration guide](https://reactnative.dev/docs/integration-with-existing-apps).
- If you're curious to learn more about React Native, check out the [docs](https://reactnative.dev/docs/getting-started).

# Troubleshooting

If you're having issues getting the above steps to work, see the [Troubleshooting](https://reactnative.dev/docs/troubleshooting) page.

## Android signed release

Release builds require an HTTPS API origin and a private release keystore. The API URL must be an origin with no path, query, or fragment; the placeholder is rejected. Debug builds continue to use the emulator URL and permit cleartext traffic, while Android release builds reject cleartext traffic.

Provide `API_BASE_URL` as a Gradle property or environment variable, and provide the signing values through environment variables or the ignored `android/keystore.properties` file. The required environment variables are `ANDROID_KEYSTORE_PATH`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, and `ANDROID_KEY_PASSWORD`. The properties file uses `storeFile`, `storePassword`, `keyAlias`, and `keyPassword`. Relative keystore paths in that file are resolved from `DriverApp/android`.

For a local Windows build, set those variables in the build shell and run:

```powershell
cd DriverApp\android
.\gradlew.bat :app:assembleRelease -PAPI_BASE_URL=$env:API_BASE_URL
```

In CI, inject the keystore as a protected file and the alias/passwords as masked secrets; set `API_BASE_URL` to the production HTTPS origin and run the same Gradle task. Do not put credentials in the repository or command-line arguments. CI must not print secret variables or the keystore contents.

Back up the release key securely and restrict access. For updates distributed outside Google Play, preserve the same signing key or users cannot install updates over the existing app. For Google Play App Signing, rotate an upload key through Play Console; changing the app-signing key requires the supported Play Console key-upgrade process. Update the protected CI keystore and associated credentials only as part of that planned rotation, and verify an update build before retiring the prior key.

# Learn More

To learn more about React Native, take a look at the following resources:

- [React Native Website](https://reactnative.dev) - learn more about React Native.
- [Getting Started](https://reactnative.dev/docs/environment-setup) - an **overview** of React Native and how setup your environment.
- [Learn the Basics](https://reactnative.dev/docs/getting-started) - a **guided tour** of the React Native **basics**.
- [Blog](https://reactnative.dev/blog) - read the latest official React Native **Blog** posts.
- [`@facebook/react-native`](https://github.com/facebook/react-native) - the Open Source; GitHub **repository** for React Native.
