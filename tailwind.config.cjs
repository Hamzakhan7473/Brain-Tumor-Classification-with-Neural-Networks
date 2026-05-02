/**
 * Tailwind shim — NeuroSight frontend currently builds with Vite + plain CSS only.
 * All colors live in frontend/src/styles/global.css :root (--green-* , --ink* , --line , --surface , --white).
 * This extend block documents iOS-aligned layout tokens mirroring STEP 2 of the NeuroSight polish spec.
 * Add tailwind postcss integration later if utilities are migrated from ios-tokens.css.
 */
module.exports = {
  content: ["./frontend/index.html", "./frontend/src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        ios: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Display",
          "SF Pro Text",
          "system-ui",
          "sans-serif",
        ],
      },
      borderRadius: {
        ios: "10px",
        "ios-lg": "16px",
        "ios-xl": "20px",
      },
      backdropBlur: {
        ios: "20px",
      },
      fontSize: {
        "ios-caption2": ["11px", { lineHeight: "13px", fontWeight: "400" }],
        "ios-caption1": ["12px", { lineHeight: "16px", fontWeight: "400" }],
        "ios-footnote": ["13px", { lineHeight: "18px", fontWeight: "400" }],
        "ios-subhead": ["15px", { lineHeight: "20px", fontWeight: "400" }],
        "ios-body": ["17px", { lineHeight: "22px", fontWeight: "400" }],
        "ios-title3": ["20px", { lineHeight: "25px", fontWeight: "400" }],
        "ios-title2": ["22px", { lineHeight: "28px", fontWeight: "400" }],
        "ios-title1": ["28px", { lineHeight: "34px", fontWeight: "400" }],
        "ios-largetitle": ["34px", { lineHeight: "41px", fontWeight: "400" }],
      },
      transitionTimingFunction: {
        "ios-spring": "cubic-bezier(0.175, 0.885, 0.32, 1.275)",
        "ios-ease": "cubic-bezier(0.4, 0, 0.2, 1)",
      },
    },
  },
  plugins: [],
};
