(() => {
  const params = new URLSearchParams(location.search);
  const fontConfig = window.WTF_FONT_CONFIG || {default: {roles: {}}};
  const defaultRoles = fontConfig.default?.roles || {};
  const fontRoles = {...defaultRoles};
  const roleVariables = {brand: "--brand", display: "--display", mono: "--mono"};

  function googleFont(link) {
    if (!link || typeof link !== "string") return null;
    try {
      const url = new URL(link.trim());
      if (url.protocol !== "https:") return null;
      let family = "";
      let stylesheet = "";
      if (url.hostname === "fonts.googleapis.com" && url.pathname === "/css2") {
        family = url.searchParams.get("family") || "";
        stylesheet = url.href;
      } else if (url.hostname === "fonts.google.com" && url.pathname.startsWith("/specimen/")) {
        family = decodeURIComponent(url.pathname.slice("/specimen/".length)).replace(/\+/g, " ");
      } else if (url.hostname === "fonts.google.com" && url.pathname === "/share") {
        family = url.searchParams.get("selection.family") || "";
      } else return null;
      family = family.split("|")[0].split(":")[0].replace(/\+/g, " ").trim();
      if (!family || !/^[A-Za-z0-9 .'-]+$/.test(family)) return null;
      if (!stylesheet) {
        const encoded = encodeURIComponent(family).replace(/%20/g, "+");
        stylesheet = `https://fonts.googleapis.com/css2?family=${encoded}&display=swap`;
      }
      return {family, stylesheet};
    } catch (_) {
      return null;
    }
  }

  const selectedFont = googleFont(fontConfig.googleFontsUrl);
  const selectedRole = roleVariables[fontConfig.googleFontRole]
    ? fontConfig.googleFontRole : "brand";
  if (selectedFont) {
    const fallback = defaultRoles[selectedRole] || "sans-serif";
    fontRoles[selectedRole] = `"${selectedFont.family}", ${fallback}`;
  }
  document.documentElement.dataset.fontVariant = selectedFont ? "google-fonts" : "current";
  if (selectedFont) document.documentElement.dataset.fontFamily = selectedFont.family;
  Object.entries(fontRoles).forEach(([role, stack]) => {
    if (roleVariables[role] && typeof stack === "string")
      document.documentElement.style.setProperty(roleVariables[role], stack);
  });
  let stylesheetReady = Promise.resolve();
  if (selectedFont) {
    stylesheetReady = new Promise(resolve => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = selectedFont.stylesheet;
      link.dataset.googleFont = selectedFont.family;
      link.addEventListener("load", resolve, {once: true});
      link.addEventListener("error", resolve, {once: true});
      document.head.append(link);
    });
  }
  // Consumers and tests can await the selected remote stylesheet without
  // delaying the current local-font default.
  window.WTF_FONTS_READY = stylesheetReady.then(() => document.fonts.ready);
  function readText(name, fallback, limit = 120) {
    const value = params.get(name);
    if (!value || !value.trim()) return fallback;
    return value.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\u2014/g, ", ")
      .replace(/\//g, " · ").replace(/\s+/g, " ").trim().slice(0, limit);
  }
  // One source for the WTF mark. Every overlay hydrates a [data-logo]
  // placeholder from it, so the 12-second signal and its motion controls
  // behave identically at 165px in the lower stack and 1000px on a card.
  const ORBIT = "M 55,195 A 395,117 0 1 1 845,195 A 395,117 0 1 1 55,195";
  const WORDMARK = "M163.68-174.24L182.40-65.52L194.88-174.24L253.44-174.24L221.28 0L147.60 0L131.28-97.20L112.32 0L41.76 0L9.60-174.24L68.16-174.24L80.40-66.96L99.60-174.24L163.68-174.24M466.80-174.24L466.80-123.84Q429.12-125.04 393.60-125.28L393.60 0L333.60 0L333.60-125.28Q297.84-125.04 260.64-123.84L260.64-174.24L466.80-174.24M661.20-174.24L661.20-129.36L530.64-129.36L530.64-104.16Q542.88-103.92 567.36-103.92Q609.60-103.92 653.28-105.36L653.28-58.32Q609.60-60 561.12-60Q540.96-60 530.64-59.76L530.64 0L474 0Q475.92-46.56 475.92-87.12Q475.92-127.68 474-174.24";
  const LOGO = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 390" fill="none" role="img" aria-label="WTF orbital logo">
<g transform="rotate(-12 450 195)">
<path d="${ORBIT}" stroke="#8B7CFF" stroke-opacity=".42" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
<path d="M 55,195 A 395,117 0 0 1 450,78" stroke="#8B7CFF" stroke-width="3" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
<g class="traveller"><g class="signal"><circle r="11" fill="#FF9D62" fill-opacity=".12"/><circle r="4.5" fill="#FF9D62"/></g><animateMotion dur="12s" repeatCount="indefinite" path="${ORBIT}"/></g>
<g class="resting-signal" transform="translate(55 195)" style="display:none"><g class="signal"><circle r="4.5" fill="#FF9D62"/></g></g>
</g>
<path d="${WORDMARK}" transform="translate(114.6 282)" fill="#F2EBDD"/>
</svg>`;
  const SPONSOR_GROUP = (duplicate = false) => `<div class="sponsor-group"${duplicate ? ' aria-hidden="true"' : ""}>
<span class="sponsor-name">Lord Socks</span><span class="sponsor-separator" aria-hidden="true"></span>
<span class="sponsor-name">House of Lords</span><span class="sponsor-separator" aria-hidden="true"></span>
<img class="sponsor-bev" src="bev-logo.svg" alt="${duplicate ? "" : "Bev."}">
</div>`;
  const SPONSORS = `<aside class="sponsor-strip" aria-label="Sponsors">
<span class="sponsor-kicker">Sponsors</span><div class="sponsor-viewport"><div class="sponsor-track">${SPONSOR_GROUP()}${SPONSOR_GROUP(true)}</div></div>
</aside>`;
  document.querySelectorAll("[data-logo]").forEach(el => {
    const tpl = document.createElement("template");
    tpl.innerHTML = LOGO;
    const svg = tpl.content.firstElementChild;
    svg.setAttribute("class", `wtf-mark ${el.className}`.trim());
    el.replaceWith(svg);
    // Strokes use non-scaling-stroke; the signal is scaled by hand so it
    // stays 4.5px wide on screen whatever size the mark is drawn at.
    const k = 900 / (svg.getBoundingClientRect().width || 900);
    svg.querySelectorAll(".signal").forEach(g => g.setAttribute("transform", `scale(${k.toFixed(4)})`));
  });
  document.querySelectorAll("[data-sponsors]").forEach(el => {
    const tpl = document.createElement("template");
    tpl.innerHTML = SPONSORS;
    const strip = tpl.content.firstElementChild;
    strip.classList.add(...el.classList);
    el.replaceWith(strip);
  });
  document.querySelectorAll("[data-copy]").forEach(el => {
    el.textContent = readText(el.dataset.copy, el.textContent, Number(el.dataset.limit) || 120);
  });
  const label = document.querySelector(".label");
  if (label) label.dataset.person = ["chirag","parth","guest"].includes(params.get("person")) ? params.get("person") : "guest";
  const clock = document.getElementById("clock-time");
  const frozen = params.has("t") && params.get("t").trim() !== "" && Number.isFinite(Number(params.get("t"))) && Number(params.get("t")) >= 0;
  function clockTick() {
    if (clock) clock.textContent = frozen ? "20:00 IST" : new Intl.DateTimeFormat("en-GB", {hour:"2-digit", minute:"2-digit", timeZoneName:"short"}).format(new Date());
  }
  clockTick();
  if (clock && !frozen) setInterval(clockTick, 1000);
  // Query copy can vary between episodes. Fit it within the broadcast frame.
  function fitCopy() {
    document.querySelectorAll("[data-fit]").forEach(el => {
      let size = parseFloat(getComputedStyle(el).fontSize);
      const min = Number(el.dataset.fit) || 16;
      while ((el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1) && size > min) {
        el.style.fontSize = --size + "px";
      }
    });
  }
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  function syncMotion() {
    document.querySelectorAll("svg").forEach(svg => {
      if (frozen || reduced.matches) svg.pauseAnimations(); else svg.unpauseAnimations();
      if (frozen) svg.setCurrentTime(Number(params.get("t")));
    });
    if (frozen) document.getAnimations().forEach(animation => {
      animation.pause(); animation.currentTime = Number(params.get("t")) * 1000;
    });
  }
  reduced.addEventListener("change", syncMotion);
  requestAnimationFrame(syncMotion);
  window.WTF_FONTS_READY.then(() => { fitCopy(); syncMotion(); });
})();
