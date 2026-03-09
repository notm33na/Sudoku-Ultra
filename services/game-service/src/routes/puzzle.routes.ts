import { Router } from 'express';
import { authenticate } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { generatePuzzleSchema } from '../schemas';
import * as ctrl from '../controllers/puzzle.controller';

const router = Router();

router.post('/generate', authenticate, validate(generatePuzzleSchema), ctrl.generate);
router.get('/:id', authenticate, ctrl.getById);

export default router;
