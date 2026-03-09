import { Router } from 'express';
import { authenticate } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { createSessionSchema, updateSessionSchema, completeSessionSchema } from '../schemas';
import * as ctrl from '../controllers/session.controller';

const router = Router();

router.post('/', authenticate, validate(createSessionSchema), ctrl.create);
router.get('/:id', authenticate, ctrl.getById);
router.patch('/:id', authenticate, validate(updateSessionSchema), ctrl.update);
router.post('/:id/hint', authenticate, ctrl.getHint);
router.post('/:id/validate', authenticate, ctrl.validate);
router.post('/:id/complete', authenticate, validate(completeSessionSchema), ctrl.complete);

export default router;
