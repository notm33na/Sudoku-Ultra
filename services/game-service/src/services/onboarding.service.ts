/**
 * Onboarding service — tracks first-time tutorial completion.
 *
 * The 9 onboarding steps are defined as static content here.
 * LLM narration is fetched on-demand from the ml-service.
 */

import { prisma } from '../prisma/client';

export const ONBOARDING_TOTAL_STEPS = 9;

export interface OnboardingStatus {
    started: boolean;
    stepsComplete: number;
    totalSteps: number;
    completed: boolean;
    skipped: boolean;
}

export async function getStatus(userId: string): Promise<OnboardingStatus> {
    const row = await prisma.onboardingProgress.findUnique({ where: { userId } });
    return {
        started: !!row,
        stepsComplete: row?.stepsComplete ?? 0,
        totalSteps: ONBOARDING_TOTAL_STEPS,
        completed: row?.completed ?? false,
        skipped: row?.skipped ?? false,
    };
}

export async function completeStep(userId: string, stepIndex: number): Promise<OnboardingStatus> {
    if (stepIndex < 0 || stepIndex >= ONBOARDING_TOTAL_STEPS) {
        throw new Error(`Step index ${stepIndex} out of range (0–${ONBOARDING_TOTAL_STEPS - 1}).`);
    }

    const newStepsComplete = stepIndex + 1;
    const done = newStepsComplete >= ONBOARDING_TOTAL_STEPS;

    await prisma.onboardingProgress.upsert({
        where: { userId },
        create: {
            userId,
            stepsComplete: newStepsComplete,
            completed: done,
            completedAt: done ? new Date() : null,
        },
        update: {
            stepsComplete: { set: Math.max(newStepsComplete, 0) },
            completed: done,
            completedAt: done ? new Date() : undefined,
        },
    });

    return getStatus(userId);
}

export async function skipOnboarding(userId: string): Promise<OnboardingStatus> {
    await prisma.onboardingProgress.upsert({
        where: { userId },
        create: {
            userId,
            stepsComplete: 0,
            completed: false,
            skipped: true,
        },
        update: { skipped: true },
    });
    return getStatus(userId);
}
