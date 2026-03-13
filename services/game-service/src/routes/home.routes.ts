import { Router } from 'express';
import { authenticate } from '../middleware/auth';
import * as ctrl from '../controllers/home.controller';

const router = Router();

// GET /api/home — returns personalised puzzle recommendations + daily + streak
router.get('/', authenticate, ctrl.home);

export default router;
