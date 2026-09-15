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
  // Links with multiple families use the first one. Remote fonts need network
  // access when the browser source loads them.
  // Leave empty to keep the current local typography.
  googleFontsUrl: "",

  // The one role replaced by the pasted font:
  // brand   = headlines, names, titles, sponsors and body copy
  // display = small textual WTF marks (the SVG orbital logo is unchanged)
  // mono    = metadata, status, clock, websites, roles and small labels
  googleFontRole: "brand",
};
