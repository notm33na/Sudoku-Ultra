import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { prisma } from '../prisma/client';
import { config } from '../config';
import { AppError } from '../middleware/errorHandler';
import { RegisterInput, LoginInput } from '../schemas';

const SALT_ROUNDS = 12;

// ─── Register ─────────────────────────────────────────────────────────────────

export async function register(input: RegisterInput) {
    const existingEmail = await prisma.user.findUnique({ where: { email: input.email } });
    if (existingEmail) throw new AppError(409, 'Email already in use');

    const existingUsername = await prisma.user.findUnique({ where: { username: input.username } });
    if (existingUsername) throw new AppError(409, 'Username already taken');

    const passwordHash = await bcrypt.hash(input.password, SALT_ROUNDS);

    const user = await prisma.user.create({
        data: {
            email: input.email,
            username: input.username,
            passwordHash,
        },
        select: { id: true, email: true, username: true, avatarUrl: true, createdAt: true },
    });

    const tokens = generateTokens(user.id, user.email);

    return { user, tokens };
}

// ─── Login ────────────────────────────────────────────────────────────────────

export async function login(input: LoginInput) {
    const user = await prisma.user.findUnique({ where: { email: input.email } });
    if (!user) throw new AppError(401, 'Invalid email or password');

    const valid = await bcrypt.compare(input.password, user.passwordHash);
    if (!valid) throw new AppError(401, 'Invalid email or password');

    const tokens = generateTokens(user.id, user.email);

    return {
        user: {
            id: user.id,
            email: user.email,
            username: user.username,
            avatarUrl: user.avatarUrl,
            createdAt: user.createdAt,
        },
        tokens,
    };
}

// ─── Refresh ──────────────────────────────────────────────────────────────────

export async function refreshToken(token: string) {
    try {
        const decoded = jwt.verify(token, config.JWT_REFRESH_SECRET) as {
            userId: string;
            email: string;
        };

        const user = await prisma.user.findUnique({ where: { id: decoded.userId } });
        if (!user) throw new AppError(401, 'User not found');

        return generateTokens(user.id, user.email);
    } catch {
        throw new AppError(401, 'Invalid or expired refresh token');
    }
}

// ─── Get Profile ──────────────────────────────────────────────────────────────

export async function getProfile(userId: string) {
    const user = await prisma.user.findUnique({
        where: { id: userId },
        select: { id: true, email: true, username: true, avatarUrl: true, createdAt: true },
    });
    if (!user) throw new AppError(404, 'User not found');
    return user;
}

// ─── Token Helpers ────────────────────────────────────────────────────────────

function generateTokens(userId: string, email: string) {
    const payload = { userId, email };

    const accessToken = jwt.sign(payload, config.JWT_SECRET, {
        expiresIn: config.JWT_EXPIRES_IN as string,
    } as jwt.SignOptions);

    const refreshTokenValue = jwt.sign(payload, config.JWT_REFRESH_SECRET, {
        expiresIn: config.JWT_REFRESH_EXPIRES_IN as string,
    } as jwt.SignOptions);

    return {
        accessToken,
        refreshToken: refreshTokenValue,
        expiresIn: parseExpiresIn(config.JWT_EXPIRES_IN),
    };
}


function parseExpiresIn(duration: string): number {
    const match = duration.match(/^(\d+)([smhd])$/);
    if (!match) return 900; // 15 min default
    const value = parseInt(match[1], 10);
    const unit = match[2];
    switch (unit) {
        case 's': return value;
        case 'm': return value * 60;
        case 'h': return value * 3600;
        case 'd': return value * 86400;
        default: return 900;
    }
}
