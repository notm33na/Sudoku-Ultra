/**
 * sentry.ts — Sentry error tracking initialisation for the mobile app.
 *
 * Call init() once before rendering the root component (in App.tsx).
 * Wraps the root component with Sentry.wrap() to capture unhandled errors.
 *
 * Configuration via Expo public env vars:
 *   EXPO_PUBLIC_SENTRY_DSN    — Sentry DSN (from sentry.io project settings)
 *   EXPO_PUBLIC_DEPLOY_ENV    — production | staging | development (default)
 *   EXPO_PUBLIC_APP_VERSION   — app version string, e.g. "1.2.3"
 *
 * In production builds, tracesSampleRate is lowered to 5% to limit overhead.
 * In development / Expo Go, all transactions are captured (100%).
 */

// Dynamic import — degrades gracefully when @sentry/react-native is not installed.
let Sentry: typeof import('@sentry/react-native') | null = null;
try {
    Sentry = require('@sentry/react-native');
} catch {
    // @sentry/react-native not installed (e.g. web build / Expo Go without native modules)
}

const DSN         = process.env.EXPO_PUBLIC_SENTRY_DSN;
const DEPLOY_ENV  = process.env.EXPO_PUBLIC_DEPLOY_ENV  ?? 'development';
const APP_VERSION = process.env.EXPO_PUBLIC_APP_VERSION ?? '0.0.1';

let _initialised = false;

/** Initialise Sentry. Call once in App.tsx before rendering. */
export function init(): void {
    if (_initialised || !Sentry || !DSN) return;
    _initialised = true;

    Sentry.init({
        dsn: DSN,
        environment: DEPLOY_ENV,
        release: `sudoku-ultra-mobile@${APP_VERSION}`,
        tracesSampleRate: DEPLOY_ENV === 'production' ? 0.05 : 1.0,
        // Capture Redux state in breadcrumbs (if using Redux)
        attachStacktrace: true,
        // React Native specific: capture JS bundle source maps
        enableNative: true,
        // Automatic session tracking (crash-free sessions metric)
        enableAutoSessionTracking: true,
        sessionTrackingIntervalMillis: 30_000,
        // Filter out noise
        beforeSend(event) {
            // Drop events from the Expo development server
            if (DEPLOY_ENV === 'development' &&
                event.exception?.values?.some((v) =>
                    v.stacktrace?.frames?.some((f) =>
                        f.filename?.includes('expo-router') ||
                        f.filename?.includes('metro')
                    )
                )
            ) {
                return null;
            }
            return event;
        },
    });
}

/** Wrap the root React component with Sentry's error boundary. */
export function wrap<T extends React.ComponentType<any>>(component: T): T {
    if (!Sentry) return component;
    return Sentry.wrap(component) as T;
}

/** Capture an exception manually (e.g. in a catch block). */
export function captureException(error: unknown, context?: Record<string, unknown>): void {
    if (!Sentry || !_initialised) {
        console.error('[Sentry disabled]', error);
        return;
    }
    Sentry.captureException(error, { extra: context });
}

/** Record a breadcrumb for debugging. */
export function addBreadcrumb(message: string, data?: Record<string, unknown>): void {
    if (!Sentry || !_initialised) return;
    Sentry.addBreadcrumb({ message, data, level: 'info' });
}

/** Set the current authenticated user for Sentry context. */
export function setUser(userId: string | null): void {
    if (!Sentry || !_initialised) return;
    Sentry.setUser(userId ? { id: userId } : null);
}
