import { Router } from 'express';
import { authenticate } from '../middleware/auth';
import * as ctrl from '../controllers/daily.controller';

const router = Router();

router.get('/', authenticate, ctrl.getDailyPuzzle);

export default router;
