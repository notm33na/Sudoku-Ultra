/**
 * Firebase Cloud Messaging service.
 *
 * Initializes firebase-admin once and exposes typed send helpers.
 * Credentials are loaded from environment variables:
 *   - FIREBASE_SERVICE_ACCOUNT_JSON  base64-encoded service account JSON (preferred)
 *   - OR FIREBASE_PROJECT_ID + FIREBASE_CLIENT_EMAIL + FIREBASE_PRIVATE_KEY (individual vars)
 *
 * If no Firebase credentials are configured, all send calls are no-ops
 * (logs a warning) so the service still starts in dev without credentials.
 */

import * as admin from 'firebase-admin';

let initialized = false;
let fcmAvailable = false;

function initFirebase(): void {
    if (initialized) return;
    initialized = true;

    const saJson = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;
    const projectId = process.env.FIREBASE_PROJECT_ID;

    if (!saJson && !projectId) {
        console.warn('[FCM] No Firebase credentials configured — FCM disabled');
        return;
    }

    try {
        let credential: admin.credential.Credential;

        if (saJson) {
            const parsed = JSON.parse(Buffer.from(saJson, 'base64').toString('utf8'));
            credential = admin.credential.cert(parsed);
        } else {
            credential = admin.credential.cert({
                projectId: projectId!,
                clientEmail: process.env.FIREBASE_CLIENT_EMAIL!,
                privateKey: (process.env.FIREBASE_PRIVATE_KEY ?? '').replace(/\\n/g, '\n'),
            });
        }

        if (admin.apps.length === 0) {
            admin.initializeApp({ credential });
        }

        fcmAvailable = true;
        console.info('[FCM] Firebase Admin initialized');
    } catch (err) {
        console.error('[FCM] Firebase initialization failed:', err);
    }
}

// ─── Public API ───────────────────────────────────────────────────────────────

export function isFcmAvailable(): boolean {
    initFirebase();
    return fcmAvailable;
}

/**
 * Send a push notification to a single FCM device token.
 * Returns the FCM message ID or null on failure.
 */
export async function sendPush(
    fcmToken: string,
    title: string,
    body: string,
    data?: Record<string, string>,
): Promise<string | null> {
    initFirebase();
    if (!fcmAvailable) return null;

    const message: admin.messaging.Message = {
        token: fcmToken,
        notification: { title, body },
        data: data ?? {},
        android: {
            priority: 'high',
            notification: {
                channelId: 'sudoku_ultra_notifications',
                sound: 'default',
            },
        },
        apns: {
            payload: { aps: { sound: 'default', badge: 1 } },
        },
    };

    try {
        return await admin.messaging().send(message);
    } catch (err: unknown) {
        // Invalid / expired token — caller should clean up
        const code = (err as { code?: string })?.code ?? '';
        if (code === 'messaging/registration-token-not-registered') {
            console.warn(`[FCM] Token expired/invalid: ${fcmToken.slice(0, 20)}...`);
        } else {
            console.error('[FCM] Send failed:', err);
        }
        return null;
    }
}

/**
 * Send a push notification to multiple device tokens (up to 500).
 */
export async function sendMulticast(
    tokens: string[],
    title: string,
    body: string,
    data?: Record<string, string>,
): Promise<{ successCount: number; failureCount: number }> {
    initFirebase();
    if (!fcmAvailable || tokens.length === 0) {
        return { successCount: 0, failureCount: 0 };
    }

    const message: admin.messaging.MulticastMessage = {
        tokens,
        notification: { title, body },
        data: data ?? {},
    };

    try {
        const result = await admin.messaging().sendEachForMulticast(message);
        return { successCount: result.successCount, failureCount: result.failureCount };
    } catch (err) {
        console.error('[FCM] Multicast failed:', err);
        return { successCount: 0, failureCount: tokens.length };
    }
}
