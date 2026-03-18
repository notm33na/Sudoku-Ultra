/** @type {import('jest').Config} */
module.exports = {
    testMatch: ['**/pact/**/*.pact.test.ts'],
    transform: { '^.+\\.tsx?$': 'ts-jest' },
    testTimeout: 30000,
    // NOTE: 'setupFilesAfterFramework' is not a valid Jest config key — Jest silently
    // ignores it.  The correct keys are 'setupFiles' (before test framework) and
    // 'setupFilesAfterFramework' (after).  Neither is required for Pact tests, so
    // this entry has been removed.
};
