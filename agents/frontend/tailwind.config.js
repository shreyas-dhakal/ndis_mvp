/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1B2B34",
        paper: "#F3F2ED",
        line: "#DCD8CE",
        slate: "#5B6B6A",
        teal: {
          50: "#EAF2F1",
          100: "#D3E4E2",
          400: "#3F8B85",
          500: "#2F6F6B",
          600: "#255853",
          700: "#1C4440",
        },
        sage: "#9CB3A4",
        ochre: {
          50: "#FBF3E7",
          400: "#C9963F",
          500: "#B8863B",
          600: "#96692C",
        },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        sans: ["'Inter'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "monospace"],
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
      },
    },
  },
  plugins: [],
};
