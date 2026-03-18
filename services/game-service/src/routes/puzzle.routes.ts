import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { authenticate } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { generatePuzzleSchema } from '../schemas';
import * as ctrl from '../controllers/puzzle.controller';
import { generatePuzzleGAN, GanMode } from '../services/puzzle.service';
import { config } from '../config';

const router = Router();

router.post('/generate', authenticate, validate(generatePuzzleSchema), ctrl.generate);
router.get('/:id', authenticate, ctrl.getById);

// ── GAN generation ────────────────────────────────────────────────────────────

const ganSchema = z.object({
    difficulty: z.enum(['easy', 'medium', 'hard', 'super_hard', 'extreme']).default('medium'),
    mode: z.enum(['solution', 'puzzle', 'constrained']).default('puzzle'),
    symmetric: z.boolean().default(false),
});

router.post(
    '/generate-gan',
    authenticate,
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const parsed = ganSchema.safeParse(req.body);
            if (!parsed.success) {
                res.status(400).json({ error: parsed.error.flatten() });
                return;
            }
            const { difficulty, mode, symmetric } = parsed.data;
            const result = await generatePuzzleGAN(difficulty, mode as GanMode, symmetric);
            res.status(201).json({ success: true, data: result, error: null, timestamp: new Date().toISOString() });
        } catch (err) {
            next(err);
        }
    },
);

// ── Semantic search proxy ─────────────────────────────────────────────────────

const semanticSchema = z.object({
    type: z.enum(['similar', 'for-user', 'by-technique', 'similar-features']),
    puzzle_id: z.string().optional(),
    user_id: z.string().optional(),
    technique_name: z.string().optional(),
    difficulty_filter: z.string().optional(),
    // similar-features fields
    difficulty: z.string().optional(),
    clue_count: z.number().int().min(17).max(81).optional(),
    techniques: z.array(z.string()).default([]),
    top_k: z.number().int().min(1).max(20).default(5),
    exclude_puzzle_ids: z.array(z.string()).default([]),
});

router.post(
    '/search',
    authenticate,
    async (req: Request, res: Response, next: NextFunction): Promise<void> => {
        try {
            const parsed = semanticSchema.safeParse(req.body);
            if (!parsed.success) {
                res.status(400).json({ error: parsed.error.flatten() });
                return;
            }
            const body = parsed.data;

            let mlPath: string;
            let mlBody: Record<string, unknown>;

            if (body.type === 'similar') {
                if (!body.puzzle_id) { res.status(400).json({ error: 'puzzle_id required' }); return; }
                mlPath = '/api/v1/search/puzzles/similar';
                mlBody = { puzzle_id: body.puzzle_id, top_k: body.top_k, difficulty_filter: body.difficulty_filter };
            } else if (body.type === 'for-user') {
                const userId = body.user_id ?? (req as any).user?.id;
                mlPath = '/api/v1/search/puzzles/for-user';
                mlBody = { user_id: userId, top_k: body.top_k, exclude_puzzle_ids: body.exclude_puzzle_ids };
            } else if (body.type === 'by-technique') {
                if (!body.technique_name) { res.status(400).json({ error: 'technique_name required' }); return; }
                mlPath = '/api/v1/search/puzzles/by-technique';
                mlBody = { technique_name: body.technique_name, top_k: body.top_k, difficulty_filter: body.difficulty_filter };
            } else {
                // similar-features
                if (!body.difficulty) { res.status(400).json({ error: 'difficulty required' }); return; }
                if (body.clue_count === undefined) { res.status(400).json({ error: 'clue_count required' }); return; }
                mlPath = '/api/v1/search/puzzles/similar-features';
                mlBody = { difficulty: body.difficulty, clue_count: body.clue_count, techniques: body.techniques, top_k: body.top_k };
            }

            const mlRes = await fetch(`${config.ML_SERVICE_URL}${mlPath}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(mlBody),
                signal: AbortSignal.timeout(8_000),
            });
            if (!mlRes.ok) throw new Error(`ml-service ${mlRes.status}`);
            const data = await mlRes.json();
            res.json({ success: true, data, error: null, timestamp: new Date().toISOString() });
        } catch (err) {
            next(err);
        }
    },
);

export default router;
