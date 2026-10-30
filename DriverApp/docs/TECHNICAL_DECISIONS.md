# Technical Decisions

## Location tracking
- What we chose: `react-native-geolocation-service` for location updates and `react-native-background-actions` to run an Android location foreground service while the driver is online.
- Why: The service lets Android continue tracking when the app is backgrounded, without adding a paid background-tracking SDK.
- Known limitation: iOS tracking is foreground-only. The Android service and GPS behavior still require real-device verification.

## Authentication
- What we chose: One opaque token per driver, created by an admin and entered in the app. The app stores it in AsyncStorage and attaches it to API requests.
- Why: Direct admin onboarding avoids a driver-facing signup, password-reset, or email-verification flow.
- Known limitation: The token has no client-side expiry or refresh flow. An admin can revoke it by deactivating the driver or generating a replacement token; the app handles an unauthorized response by clearing its saved token.

## State management
- What we chose: React's built-in `useState` and `useEffect`, with token state at the app/navigation root and screen-specific state kept inside each screen.
- Why: The app has a small three-screen flow and limited shared state, so a dedicated state library would add complexity without a matching benefit at this size.

## Networking
- What we chose: `fetch()` through a small typed API client, with no Axios or React Query. The client adds the `x-token` header, sends JSON requests, and aborts requests after 10 seconds.
- Why: The current API surface is small, so this wrapper is sufficient without a larger networking or caching dependency.

## Navigation
- What we chose: React Navigation 7 native stack with TokenEntry, Main, and Settings routes.
- Why: It provides a standard React Native navigation setup with TypeScript support for the app's token-gated flow.

## Unauthorized response handling
- What we chose: The API client invokes a single unauthorized handler on HTTP 401. The app removes the saved token, notifies the driver, and returns navigation to token entry.
- Why: Centralizing this behavior gives each endpoint caller consistent handling after admin-side token revocation.

## Location delivery and failures
- What we chose: Location points are persisted in a bounded AsyncStorage queue with a cap of 1,000 entries and sent in batches of up to 50. Failed deliveries use increasing retry backoff. If a batch receives HTTP 422, the client bisects it recursively to isolate invalid points; rejected points are dropped while valid points can still be delivered.
- Why: Persistence and retry protect queued points across temporary network failures, while bisection prevents one invalid point from blocking an entire batch.
- Known limitation: The queue drops oldest points when it reaches its cap, and server-rejected points are not retried.

## Location permissions
- What we chose: The app requests location permission when the driver switches online. iOS requests `whenInUse`; Android requests fine and coarse location and requires fine permission.
- Why: This avoids prompting before location tracking is needed and limits permission scope on iOS.
- Known limitation: iOS background tracking is not implemented. Denied permissions block going online until the driver grants access in system settings.

## Backend URL configuration
- What we chose: Android debug builds default to `http://10.0.2.2:8000`, while release builds require an HTTPS origin supplied as `API_BASE_URL`. Settings can change the URL and persists it in AsyncStorage separately from the driver token; release URLs are validated as HTTPS origins without a path.
- Why: The Android emulator can reach the host machine through `10.0.2.2`, while release traffic must use the production HTTPS API.
