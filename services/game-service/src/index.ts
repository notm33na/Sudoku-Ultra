import './instrumentation';  // must be first — patches modules before they load
import { createApp } from './app';
import { config } from './config';
import { kafkaService } from './services/kafka.service';
import { startApolloServer } from './graphql/server';

async function main() {
    const app = createApp();

    // Apollo Server 4 must be started before expressMiddleware is applied.
    await startApolloServer(app);

    const server = app.listen(config.PORT, () => {
        console.info(`🎮 Game Service running on port ${config.PORT}`);
        console.info(`   Environment: ${config.NODE_ENV}`);
        console.info(`   Health check: http://localhost:${config.PORT}/health`);
        console.info(`   GraphQL:      http://localhost:${config.PORT}/graphql`);

        // Connect Kafka producer — fire-and-forget, non-fatal if broker is unavailable.
        kafkaService.connect().catch((err) => {
            console.warn('[Kafka] Initial connect error (analytics disabled):', err);
        });
    });

    // ─── Graceful Shutdown ────────────────────────────────────────────────────

    async function shutdown(signal: string): Promise<void> {
        console.info(`[Game Service] ${signal} received — shutting down`);
        server.close(async () => {
            await kafkaService.disconnect();
            console.info('[Game Service] Clean exit');
            process.exit(0);
        });
    }

    process.on('SIGTERM', () => shutdown('SIGTERM'));
    process.on('SIGINT', () => shutdown('SIGINT'));
}

main().catch((err) => {
    console.error('[Game Service] Fatal startup error:', err);
    process.exit(1);
});
