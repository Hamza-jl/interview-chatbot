/**
 * Devoteam brand tokens - values taken from the Devoteam Branding Zone.
 *
 * Primary    Red Poppy #f8485e · Dark Grey #3c3c3a · White #ffffff
 * Secondary  backgrounds and graphics only (including circles) - never text
 * Accent     reserved for colour-coding, data visualisation, charts
 *
 * The interface is White-forward, as the charter asks: "White should serve as an
 * active colour to reinforce the premium positioning of the brand." Full black
 * is never used - the darkest tone in the product is Dark Grey, and the neutral
 * ramp is built from it (a warm grey, R60 G60 B58).
 *
 * The `ink` ramp runs light -> dark as the number grows *inverted*: ink-950 is
 * the page (White) and ink-100 is body text (Dark Grey). Contrast on White:
 * ink-100 11.0:1, ink-300 6.7:1, ink-400 4.5:1 - all at or above WCAG AA.
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ---- Primary ----------------------------------------------------
        poppy: {
          DEFAULT: "#f8485e",
          500: "#f8485e", // Red Poppy - Pantone 1785 C
          600: "#e5344a", // pressed state only
          400: "#fca2ae", // Poppy Light   (secondary)
          300: "#fddade", // Poppy Lighter (secondary)
        },

        // ---- Secondary: backgrounds and graphics only -------------------
        aqua: "#d7ebe7",
        beige: "#efeadc",

        // ---- Accent: colour-coding, data visualisation ------------------
        accent: {
          fire: "#fcc354",   // Intense Fire - warnings, degraded state
          mint: "#5ab891",   // Fresh Mint   - success, completed
          lagoon: "#4a8cca", // Blue Lagoon  - information
          candy: "#ec86a3",  // Candy
          violet: "#63238c", // Violet
        },

        // ---- Neutral ramp: White page down to Dark Grey text ------------
        ink: {
          950: "#ffffff", // page
          900: "#fbfbfa", // recessed surface
          850: "#ffffff", // panel
          800: "#efeeee", // raised surface - Light Grey (secondary)
          700: "#e8e7e5", // hover
          600: "#e3e2df", // border
          500: "#c9c8c4", // strong border
          400: "#77776f", // muted text       4.5:1 on white
          300: "#5c5c58", // secondary text   6.7:1 on white
          200: "#4a4a47",
          100: "#3c3c3a", // body text - Dark Grey, 11.0:1 on white
        },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "sans-serif"],
        display: ["Sora", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
      boxShadow: {
        // Soft, warm-grey shadows: a light interface must not use black.
        glow: "0 0 0 1px rgba(248,72,94,.22), 0 10px 24px -12px rgba(248,72,94,.55)",
        "glow-lg": "0 16px 40px -14px rgba(248,72,94,.55)",
        panel: "0 18px 48px -26px rgba(60,60,58,.30), 0 2px 6px -2px rgba(60,60,58,.06)",
        card: "0 1px 2px rgba(60,60,58,.06)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        breathe: {
          "0%,100%": { opacity: ".55", transform: "scale(1)" },
          "50%": { opacity: ".8", transform: "scale(1.05)" },
        },
        blink: { "0%,100%": { opacity: "1" }, "50%": { opacity: ".25" } },
      },
      animation: {
        "fade-up": "fade-up .45s cubic-bezier(.22,1,.36,1) both",
        breathe: "breathe 9s ease-in-out infinite",
        blink: "blink 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
