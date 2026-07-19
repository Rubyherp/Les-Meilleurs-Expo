/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        lesBackground: "#F7F4EE",
        lesInk: "#17171D",
        lesCoral: "#FF5C5C",
        lesLime: "#C8F36A",
        lesMuted: "#747475",
        lesLine: "#DAD6CC",
      },
    },
  },
  plugins: [],
};
