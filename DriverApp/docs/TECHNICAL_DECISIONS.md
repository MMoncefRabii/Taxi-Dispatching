# Technical Decisions

## Location tracking library
- What we chose: `react-native-geolocation-service` 5.3.1, using foreground `watchPosition` updates rather than a paid background-tracking SDK.
- Why: Transistorsoft's `react-native-background-geolocation` offers more reliable long-running background tracking but requires a paid license; we are starting lean for the MVP and will revisit it if drivers report lost tracking during long background periods.
- Known limitation: Tracking is currently foreground-only: iOS requests `whenInUse` authorization, Android requests fine and coarse location, and no background mode or foreground service is configured.

## Auth model
- What we chose: One long-lived token per driver, created by the admin through the backend and pasted into the app on first launch; the app stores it in AsyncStorage and reuses it in requests.
- Why: This avoids a driver-facing signup/login flow, password resets, and email verification, which is reasonable for a small pilot where the admin directly onboards drivers.
- Known limitation: There is no expiry or refresh mechanism, and the backend currently has no driver-token deactivation endpoint, so revocation is not available through the implemented app/backend workflow.

## State management
- What we chose: React's built-in `useState` and `useEffect`, with token state at the app/navigation root and screen-specific state kept inside each screen; no Redux, Zustand, or shared context is used.
- Why: The app has a small three-screen flow and limited shared state, so a dedicated state library would add complexity without a matching benefit at this size.
- Known limitation: Online status is screen-local and is not restored from the backend when the app starts again.

## Networking
- What we chose: `fetch()` through a small typed API client, with no Axios or React Query; the client adds the `x-token` header and handles JSON POSTs to the status and location endpoints.
- Why: The current API surface is small, so this wrapper is sufficient without a larger networking or caching dependency; reconsider caching or retry tooling if endpoints and client-side data needs grow.
- Known limitation: The API client has no general retry, request timeout, or caching layer, and converts network and non-2xx responses into `ApiError` instances.

## Navigation
- What we chose: React Navigation 7 native stack (`@react-navigation/native` 7.5.0 and `@react-navigation/native-stack` 7.20.0) with TokenEntry, Main, and Settings routes.
- Why: It is a standard React Native navigation option with TypeScript support and a minimal setup for the app's token-gated three-screen flow.

## Unauthorized response handling
- What we chose: The API client invokes a single unauthorized handler on HTTP 401, and the app registers that handler at the root to remove the saved token, show an invalid-driver-token alert, and return navigation to token entry.
- Why: Centralizing this behavior means each endpoint caller gets consistent invalid-token handling without duplicating logout logic.

## Location delivery and failures
- What we chose: The tracker sends each watch callback to the location endpoint, skips callbacks while a send is already in flight, and resets its consecutive-failure counter after a successful HTTP response.
- Why: Serializing sends avoids overlapping requests, while a warning after three consecutive failures gives the driver a visible sync signal without adding a queue or retry subsystem.
- Known limitation: Failed points are dropped rather than queued or retried; a successful response with `ok: false` (for example, a low-accuracy point ignored by the backend) is not counted as a failure and does not update the displayed last-sent location.

## Location permissions
- What we chose: The app requests location permission only when the driver switches online; iOS asks for `whenInUse`, while Android requests fine and coarse permission and requires fine permission to be granted before going online.
- Why: This avoids prompting before location tracking is needed and keeps the permission scope aligned with foreground-only sharing.
- Known limitation: There is no background-location permission flow, and denied permission blocks the online transition until access is granted in system settings.

## Backend URL configuration
- What we chose: The backend URL defaults to `http://10.0.2.2:8000` and can be changed in Settings; the value is persisted in AsyncStorage separately from the driver token.
- Why: The Android emulator can reach a host machine through `10.0.2.2`, and making the URL editable supports changing development or deployment targets without rebuilding the app.
