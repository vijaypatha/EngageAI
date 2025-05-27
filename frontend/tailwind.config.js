/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ['class'],
    content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
        colors: {
            // ... your existing colors ...
            primary: { /* ... */ },
            secondary: { /* ... */ },
            neutral: '#94a3b8',
            dark: { /* ... */ },
            background: 'hsl(var(--background))',
            foreground: 'hsl(var(--foreground))',
            card: { /* ... */ },
            popover: { /* ... */ },
            muted: { /* ... */ },
            accent: { /* ... */ },
            destructive: { /* ... */ },
            border: 'hsl(var(--border))',
            input: 'hsl(var(--input))',
            ring: 'hsl(var(--ring))',
            chart: { /* ... */ }
        },
        backgroundImage: {
            'nudge-gradient': 'radial-gradient(circle at top, #1A1D2E, #0C0F1F)',
            'primary-gradient': 'linear-gradient(to right, var(--tw-gradient-from), var(--tw-gradient-to))'
        },
        animation: {
            float: 'float 3s ease-in-out infinite',
            'gradient-x': 'gradient-x 3s ease infinite',
            pulse: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
            'logo-shine': 'logo-shine 3s ease-in-out infinite', // Your original shine
            'logo-shine-subtle': 'logo-shine-subtle 2.5s ease-out infinite', // Previous attempt

            // --- NEW GENTLE PULSE ANIMATION FOR LOGO ---
            'gentle-logo-pulse': 'gentle-logo-pulse 3s ease-in-out infinite',
        },
        keyframes: {
            float: { /* ... */ },
            'gradient-x': { /* ... */ },
            pulse: { /* ... */ },
            'logo-shine': { /* ... */ },
            'logo-shine-subtle': { /* ... */ },

            // --- NEW GENTLE PULSE KEYFRAMES ---
            'gentle-logo-pulse': {
                '0%, 100%': { opacity: '0.03' }, // Start and end with very low opacity (3%)
                '50%': { opacity: '0.1' },     // Pulse to a slightly higher opacity (10%)
            },
        },
        boxShadow: {
            // ... your existing boxShadows ...
            glow: '0 0 20px rgba(34, 197, 94, 0.2)',
            xl: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)'
        },
        borderRadius: {
            // ... your existing borderRadius ...
            lg: 'var(--radius)',
            md: 'calc(var(--radius) - 2px)',
            sm: 'calc(var(--radius) - 4px)'
        }
    }
  },
  plugins: [require("tailwindcss-animate")],
};