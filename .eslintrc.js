/** @type {import('eslint').Linter.Config} */
module.exports = {
    root: true,
    parser: '@typescript-eslint/parser',
    parserOptions: {
        ecmaVersion: 2022,
        sourceType: 'module',
    },
    plugins: ['@typescript-eslint'],
    extends: [
        'eslint:recommended',
        'plugin:@typescript-eslint/recommended',
        'prettier',
    ],
    env: {
        node: true,
        es2022: true,
    },
    rules: {
        '@typescript-eslint/no-unused-vars': [
            'error',
            { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
        ],
        '@typescript-eslint/explicit-function-return-type': 'off',
        '@typescript-eslint/no-explicit-any': 'warn',
        'no-console': ['warn', { allow: ['warn', 'error', 'info'] }],
    },
    overrides: [
        {
            files: ['**/*.test.ts', '**/*.spec.ts', '**/__tests__/**'],
            env: {
                jest: true,
            },
            rules: {
                '@typescript-eslint/no-explicit-any': 'off',
            },
        },
    ],
    ignorePatterns: ['dist/', 'node_modules/', 'coverage/', '.turbo/'],
};
