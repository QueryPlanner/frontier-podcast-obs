// Typography variants for every browser overlay.
//
// `current` is deliberately local-only and remains the default. To try another
// font, add a named entry with its stylesheet URL and the CSS font roles it
// should override, then pass that name as ?font=<name> or --font <name>.
window.WTF_FONT_CONFIG = {
  defaultVariant: "current",
  variants: {
    current: {
      roles: {
        brand: '"Anybody", sans-serif',
        display: '"Dela Gothic One", sans-serif',
        mono: '"Fragment Mono", monospace',
      },
    },
    "cormorant-garamond": {
      stylesheet: "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap",
      roles: {
        brand: '"Cormorant Garamond", "Anybody", serif',
      },
    },
  },
};
