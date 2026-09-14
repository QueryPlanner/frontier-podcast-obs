# Asset provenance

The WTF mark, palette, orbital animation and planet renderer are based on the
approved HTML brand board in the parent workspace. The mark is embedded as a
template in `brand.js` rather than a separate SVG file so the signal animates
and freezes identically wherever it is drawn. The planet is rendered on the
GPU by the fragment shader in `planet.js`.

`bev-logo.svg` contains the supplied attachment artwork named
`Brand Identity/SVG/Full logo.svg`. It preserves the original blue, red and
yellow shapes followed by the dark Bev. wordmark. CSS supplies a bone-colored
panel and clear space for contrast against the dark studio background.
The SVG is unchanged from the attachment; it is not recreated with a font.

The fonts were downloaded from the Google Fonts repository, with their
original SIL Open Font License files alongside them:

- Anybody: `ofl/anybody/Anybody[wdth,wght].ttf`
- Dela Gothic One: `ofl/delagothicone/DelaGothicOne-Regular.ttf`
- Fragment Mono: `ofl/fragmentmono/FragmentMono-Regular.ttf`

The local font files let OBS render the intended typography without a network
request. All artwork, styles and scripts used by the overlays are local.
Brand names and logos remain the property of their respective owners.
