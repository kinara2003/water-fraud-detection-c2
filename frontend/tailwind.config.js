/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Calm, Clean Utility Surface & Neutral Palette
        surface: {
          bg: "#f8fafc",      // Neutral background (slate-50)
          card: "#ffffff",    // Card surfaces (white)
          border: "#e2e8f0",  // Borders (slate-200)
          muted: "#f1f5f9",   // Muted container (slate-100)
        },
        // Typography Colors
        content: {
          primary: "#0f172a",   // Primary text (slate-900)
          secondary: "#64748b", // Secondary text (slate-500)
          muted: "#94a3b8",     // Tertiary / muted (slate-400)
        },
        // Operational Status Colors
        status: {
          // Normal / Safe
          safe: "#059669",          // emerald-600
          "safe-tint": "#ecfdf5",   // emerald-50
          normal: "#059669",
          "normal-tint": "#ecfdf5",
          // Caution / Refill Surge
          caution: "#d97706",        // amber-600
          "caution-tint": "#fffbeb", // amber-50
          warning: "#d97706",
          "warning-tint": "#fffbeb",
          // High Suspicion / Action Needed
          suspicious: "#e11d48",        // rose-600
          "suspicious-tint": "#fff1f2", // rose-50
          critical: "#e11d48",
          danger: "#e11d48",
        },
        // System / Brand Colors
        brand: {
          blue: "#2563eb",  // blue-600
          sky: "#0ea5e9",   // sky-500
          navy: "#0f172a",  // slate-900
        },
        // Backward compatibility mappings
        nwsdb: {
          navy: "#0f172a",
          blue: "#2563eb",
          accent: "#0ea5e9",
          cyan: "#38bdf8",
          normal: "#059669",
          warning: "#d97706",
          danger: "#e11d48",
        },
        primary: {
          DEFAULT: "#0f172a",
          navy: "#0f172a",
          blue: "#2563eb",
        },
        accent: {
          DEFAULT: "#0ea5e9",
          blue: "#2563eb",
          cyan: "#0ea5e9",
        },
      },
    },
  },
  plugins: [],
}
