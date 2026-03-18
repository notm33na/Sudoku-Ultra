/**
 * Pact provider verification — game-service
 *
 * Starts the game-service (or points at a running instance) and verifies
 * all consumer contracts in pact/pacts/.
 *
 * The provider-state endpoint (/_pact/provider-states) is implemented in
 * services/game-service/src/routes/pact.routes.ts and is registered only
 * when NODE_ENV=test.  It seeds the required Prisma data for each state.
 *
 * Run:
 *   NODE_ENV=test \
 *   DATABASE_URL=postgresql://... \
 *   PACT_PROVIDER_URL=http://localhost:3001 \
 *   npx jest pact/provider/game-service.verify.test.ts
 */

import { Verifier } from '@pact-foundation/pact';
import path from 'path';

const PROVIDER_URL = process.env.PACT_PROVIDER_URL ?? 'http://localhost:3001';
const PACT_BROKER_URL = process.env.PACT_BROKER_URL ?? '';
const PACT_BROKER_TOKEN = process.env.PACT_BROKER_TOKEN ?? '';

describe('Pact provider verification — game-service', () => {
    it('satisfies all consumer contracts', async () => {
        const verifier = new Verifier({
            providerBaseUrl: PROVIDER_URL,
            provider: 'game-service',

            // Load pacts from local directory (CI may pull from broker instead).
            pactUrls: [
                path.resolve(__dirname, '../pacts/mobile-app-game-service.json'),
            ],

            // Optionally publish results to Pact Broker.
            ...(PACT_BROKER_URL && {
                publishVerificationResult: true,
                providerVersion: process.env.GIT_SHA ?? 'local',
                pactBrokerUrl: PACT_BROKER_URL,
                pactBrokerToken: PACT_BROKER_TOKEN,
            }),

            // The provider-states endpoint seeds real Prisma data for each
            // state before the verifier replays the interaction.
            // Implemented in pact.routes.ts; active only when NODE_ENV=test.
            providerStatesSetupUrl: `${PROVIDER_URL}/_pact/provider-states`,
        });

        await verifier.verifyProvider();
    }, 60_000);
});
