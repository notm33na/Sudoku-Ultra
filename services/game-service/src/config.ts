import { z } from 'zod';

const envSchema = z.object({
    PORT: z.coerce.number().default(3001),
    NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
    DATABASE_URL: z.string().default('postgresql://sudoku:sudoku@localhost:5432/sudoku_ultra'),
    JWT_SECRET: z.string().default('dev-jwt-secret-change-in-production'),
    JWT_REFRESH_SECRET: z.string().default('dev-refresh-secret-change-in-production'),
    JWT_EXPIRES_IN: z.string().default('15m'),
    JWT_REFRESH_EXPIRES_IN: z.string().default('7d'),
    CORS_ORIGIN: z.string().default('*'),
    REDIS_URL: z.string().default('redis://localhost:6379'),
    INTERNAL_SECRET: z.string().default('dev-internal-secret-change-in-production'),
    ML_SERVICE_URL: z.string().default('http://ml-service:3003'),
});

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
    console.error('❌ Invalid environment variables:', parsed.error.flatten().fieldErrors);
    process.exit(1);
}

export const config = parsed.data;
export type Config = z.infer<typeof envSchema>;
