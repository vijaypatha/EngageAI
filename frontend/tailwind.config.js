/** @type {import('tailwindcss').Config} */

module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#22c55e',
        secondary: '#60a5fa',
        neutral: '#94a3b8',
        dark: {
          DEFAULT: '#0C0F1F',
          lighter: '#1A1E2E',
          darker: '#080A14',
        },
      },
      backgroundImage: {
        'nudge-gradient': 'radial-gradient(circle at top, #1A1D2E, #0C0F1F)',
        'primary-gradient': 'linear-gradient(to right, var(--tw-gradient-from), var(--tw-gradient-to))',
      },
      animation: {
        'float': 'float 3s ease-in-out infinite',
        'gradient-x': 'gradient-x 3s ease infinite',
        'pulse': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite', // For the heart icon
        'logo-shine': 'logo-shine 3s ease-in-out infinite', // Refined shimmer
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'gradient-x': {
          '0%, 100%': {
            'background-position': '200% 0',
          },
          '50%': {
            'background-position': '0 0',
          },
        },
        pulse: { // For the heart icon
          '0%, 100%': { opacity: 1, transform: 'scale(1)' },
          '50%': { opacity: .7, transform: 'scale(1.1)' },
        },
        'logo-shine': { // Refined shimmer keyframes
          '0%': { transform: 'translateX(-100%) skewX(-20deg)' }, // Start off-screen, skewed
          '50%': { transform: 'translateX(100%) skewX(-20deg)' }, // Sweep across
          '100%': { transform: 'translateX(200%) skewX(-20deg)' },// Ensure it fully exits
        },
      },
      boxShadow: {
        'glow': '0 0 20px rgba(34, 197, 94, 0.2)',
        'xl': '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
      },
    },
  },
  plugins: [],
};