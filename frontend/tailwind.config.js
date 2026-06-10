/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink:    "#0d0d0d",
        paper:  "#f5f2eb",
        accent: "#c84b31",
        muted:  "#8a8070",
        border: "#d8d0c4",
      },
      fontFamily: {
        sans:  ["'IBM Plex Sans'", "sans-serif"],
        mono:  ["'IBM Plex Mono'", "monospace"],
        serif: ["'Playfair Display'", "serif"],
      },
    },
  },
  plugins: [],
}
