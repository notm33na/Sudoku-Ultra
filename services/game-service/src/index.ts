import { createApp } from './app';
import { config } from './config';

const app = createApp();

app.listen(config.PORT, () => {
    console.info(`🎮 Game Service running on port ${config.PORT}`);
    console.info(`   Environment: ${config.NODE_ENV}`);
    console.info(`   Health check: http://localhost:${config.PORT}/health`);
});

export default app;
