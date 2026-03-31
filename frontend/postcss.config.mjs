// Keep PostCSS local to the frontend.
// We don't rely on Tailwind here; an empty plugin list prevents Vite from
// accidentally loading a parent PostCSS config.
export default {
  plugins: [],
};

