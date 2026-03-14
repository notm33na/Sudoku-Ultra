/**
 * server.ts — Apollo Server 4 factory + Express middleware.
 *
 * Call `startApolloServer(app)` once during app initialisation.
 * The GraphQL endpoint is mounted at `/graphql`.
 *
 * Apollo Server 4 must be started before `expressMiddleware` is called,
 * so this function is async.
 */

import { ApolloServer } from '@apollo/server';
import { expressMiddleware } from '@apollo/server/express4';
import type { Express } from 'express';
import { typeDefs } from './schema';
import { resolvers } from './resolvers';

export async function startApolloServer(app: Express): Promise<void> {
    const server = new ApolloServer({ typeDefs, resolvers });

    await server.start();

    // `express.json()` is already applied globally in createApp(),
    // so no need to add it here.
    app.use('/graphql', expressMiddleware(server));
}
