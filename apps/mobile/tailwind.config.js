/** @type {import('tailwindcss').Config} */
module.exports = {
    content: ['./App.{js,jsx,ts,tsx}', './src/**/*.{js,jsx,ts,tsx}'],
    theme: {
        extend: {
            colors: {
                primary: {
                    50: '#eff6ff',
                    100: '#dbeafe',
                    200: '#bfdbfe',
                    300: '#93c5fd',
                    400: '#60a5fa',
                    500: '#3b82f6',
                    600: '#2563eb',
                    700: '#1d4ed8',
                    800: '#1e40af',
                    900: '#1e3a8a',
                },
                surface: {
                    light: '#f8fafc',
                    dark: '#0f172a',
                },
                cell: {
                    given: '#334155',
                    empty: '#ffffff',
                    selected: '#dbeafe',
                    highlighted: '#e0f2fe',
                    error: '#fecaca',
                },
            },
            fontFamily: {
                sans: ['Inter', 'system-ui'],
                mono: ['JetBrains Mono', 'monospace'],
            },
        },
    },
    plugins: [],
};
