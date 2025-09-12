/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/templates/**/*.html",  // Recursive match all HTML files
    "./src/static/js/*.js"
  ],
  theme: {
    extend: {
      height: {
        'screen-120': 'calc(100vh - 120px)',
      }
    },
  },
  plugins: [
    require('tailwind-scrollbar'),
  ],
}
