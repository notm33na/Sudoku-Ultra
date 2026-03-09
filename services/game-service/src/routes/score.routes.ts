import { Router } from 'express';
import { authenticate } from '../middleware/auth';
import { validateQuery } from '../middleware/validate';
import { leaderboardQuerySchema } from '../schemas';
import * as ctrl from '../controllers/score.controller';

const router = Router();

router.get('/leaderboard', authenticate, validateQuery(leaderboardQuerySchema), ctrl.getLeaderboard);
router.get('/me', authenticate, ctrl.getMyScores);

export default router;
