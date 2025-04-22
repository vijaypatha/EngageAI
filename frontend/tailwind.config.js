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
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        }
      },
      boxShadow: {
        'glow': '0 0 20px rgba(34, 197, 94, 0.2)',
      },
    },
  },
  plugins: [],
};