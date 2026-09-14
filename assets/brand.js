(() => {
  const params = new URLSearchParams(location.search);
  function readText(name, fallback, limit = 120) {
    const value = params.get(name);
    if (!value || !value.trim()) return fallback;
    return value.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\u2014/g, ", ")
      .replace(/\//g, " · ").replace(/\s+/g, " ").trim().slice(0, limit);
  }
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
  document.fonts.ready.then(() => { fitCopy(); syncMotion(); });
})();
