// Typography for every browser overlay. The bundled fonts below are always the
// fallback and need no network connection.
window.WTF_FONT_CONFIG ||= {
  default: {
    roles: {
      brand: '"Anybody", sans-serif',
      display: '"Dela Gothic One", sans-serif',
      mono: '"Fragment Mono", monospace',
    },
  },

  // Paste a Google Fonts specimen/share URL or a fonts.googleapis.com CSS URL.
  // Example: "https://fonts.google.com/specimen/Cormorant+Garamond"
  // Leave empty to keep the current local typography.
  googleFontsUrl: "",

  // Which typography role the pasted font replaces: brand, display or mono.
  googleFontRole: "brand",
};
