/** @type {import('tailwindcss').Config} */

module.exports = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx}",
    "./src/components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      backgroundImage: {
        'nudge-gradient': 'radial-gradient(circle at top center, #0f172a 0%, #000000 100%)',
      },
      colors: {
        primary: '#22c55e',
        secondary: '#60a5fa',
        neutral: '#94a3b8',
      },
    },
  },
  plugins: [],
};