/**
 * Admin routes — privileged operations requiring ADMIN role.
 *
 * All routes require:
 *   1. Valid JWT (authenticate middleware)
 *   2. Admin role claim in JWT payload (requireAdmin middleware)
 *
 * Endpoints:
 *   POST /api/admin/gdpr/delete  — GDPR right-to-erasure for a user
 */

import { Router } from 'express';
import { authenticate, AuthenticatedRequest } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { z } from 'zod';
import { Response, NextFunction } from 'express';
import { prisma } from '../db';

const router = Router();

// ── Admin guard ───────────────────────────────────────────────────────────────

/**
 * Middleware: reject non-admin callers.
 * Expects JWT payload to include `role: "admin"`.
 * The auth.controller sets this claim on login for admin accounts.
 */
function requireAdmin(req: AuthenticatedRequest, res: Response, next: NextFunction): void {
    const user = req.user as (typeof req.user & { role?: string }) | undefined;
    if (!user || user.role !== 'admin') {
        res.status(403).json({
            success: false,
            data: null,
            error: 'Admin privileges required',
            timestamp: new Date().toISOString(),
        });
        return;
    }
    next();
}

// ── GDPR deletion ─────────────────────────────────────────────────────────────

const gdprDeleteSchema = z.object({
    userId: z.string().uuid('userId must be a valid UUID'),
    reason: z.string().max(500).optional(),
});

/**
 * POST /api/admin/gdpr/delete
 *
 * Erases all personal data for a user (GDPR Article 17 — Right to Erasure).
 *
 * Deletes or nulls:
 *   - users row (and cascades: game_sessions, streaks, friendships, etc.)
 *   - feature_store rows for this entity
 *   - ab_test_result rows
 *   - gdpr_deletion_log entry created for audit trail
 *
 * The ML service warehouse sync (warehouse_etl DAG) will remove
 * pseudonymised warehouse rows on next run, or call gdpr_deletion.py directly.
 *
 * Body: { userId: string (UUID), reason?: string }
 * Response: { success: true, data: { deletedUserId, tablesAffected: string[] } }
 */
router.post(
    '/gdpr/delete',
    authenticate,
    requireAdmin,
    validate(gdprDeleteSchema),
    async (req: AuthenticatedRequest, res: Response) => {
        const { userId, reason } = req.body as z.infer<typeof gdprDeleteSchema>;
        const requestedBy = req.user!.userId;
        const tablesAffected: string[] = [];

        try {
            // Verify user exists before deletion
            const user = await prisma.user.findUnique({ where: { id: userId } });
            if (!user) {
                res.status(404).json({
                    success: false,
                    data: null,
                    error: `User ${userId} not found`,
                    timestamp: new Date().toISOString(),
                });
                return;
            }

            // Execute cascading deletion in a transaction
            await prisma.$transaction(async (tx) => {
                // Feature store — entity rows
                const fsDeleted = await tx.$executeRaw`
                    DELETE FROM feature_store WHERE entity_id = ${userId} AND entity_type = 'user'
                `;
                if (fsDeleted > 0) tablesAffected.push(`feature_store (${fsDeleted})`);

                // A/B test results
                const abDeleted = await tx.$executeRaw`
                    DELETE FROM ab_test_result WHERE user_id = ${userId}
                `;
                if (abDeleted > 0) tablesAffected.push(`ab_test_result (${abDeleted})`);

                // Friendships (both directions)
                const friendsDeleted = await tx.$executeRaw`
                    DELETE FROM friendships WHERE user_id = ${userId} OR friend_id = ${userId}
                `;
                if (friendsDeleted > 0) tablesAffected.push(`friendships (${friendsDeleted})`);

                // User row — ON DELETE CASCADE handles: game_sessions, streaks,
                // player_ratings, daily_puzzle_attempts, user_lessons,
                // activity_feeds, notifications
                await tx.user.delete({ where: { id: userId } });
                tablesAffected.push('users + cascaded tables');

                // Audit log
                await tx.$executeRaw`
                    INSERT INTO gdpr_deletion_log (user_id, requested_by, reason, completed_at)
                    VALUES (${userId}, ${requestedBy}, ${reason ?? null}, NOW())
                `;
                tablesAffected.push('gdpr_deletion_log');
            });

            res.json({
                success: true,
                data: {
                    deletedUserId: userId,
                    tablesAffected,
                    requestedBy,
                    completedAt: new Date().toISOString(),
                },
                error: null,
                timestamp: new Date().toISOString(),
            });
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Internal error';
            res.status(500).json({
                success: false,
                data: null,
                error: message,
                timestamp: new Date().toISOString(),
            });
        }
    }
);

export default router;
