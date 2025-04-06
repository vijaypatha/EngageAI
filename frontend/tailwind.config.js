/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
      "./src/**/*.{ts,tsx}", // ensure this points to your code
    ],
    theme: {
      extend: {},
    },
    plugins: [
      require('@tailwindcss/line-clamp'), // ✅ add this
    ],
  };
  