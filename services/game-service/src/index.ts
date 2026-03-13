import { createApp } from './app';
import { config } from './config';
import { kafkaService } from './services/kafka.service';

const app = createApp();

const server = app.listen(config.PORT, () => {
    console.info(`🎮 Game Service running on port ${config.PORT}`);
    console.info(`   Environment: ${config.NODE_ENV}`);
    console.info(`   Health check: http://localhost:${config.PORT}/health`);

    // Connect Kafka producer — fire-and-forget, non-fatal if broker is unavailable.
    kafkaService.connect().catch((err) => {
        console.warn('[Kafka] Initial connect error (analytics disabled):', err);
    });
});

// ─── Graceful Shutdown ────────────────────────────────────────────────────────

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

export default app;
