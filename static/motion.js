/* RetentionApp motion: subtle, optional, and inexpensive to render. */
(() => {
  const motionPreference = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;

  if (motionPreference && motionPreference.matches) return;

  const selector = [
    ".discover-intro",
    ".location-note",
    ".search-box",
    ".filters",
    ".results-panel",
    ".business-card",
    ".offer-card",
    ".profile-card",
    ".owner-card",
    ".business-card-owner",
    ".auth-panel",
    ".auth-story",
    ".auth-perk",
    ".dashboard-header",
    ".business-profile",
    ".profile-page",
    ".closing-note",
    ".business-section",
    ".offer-box"
  ].join(",");

  const elements = Array.from(document.querySelectorAll(selector));
  if (!elements.length || !("IntersectionObserver" in window)) return;

  document.body.classList.add("ra-motion-ready");

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("ra-visible");
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.06, rootMargin: "0px 0px -16px 0px" });

  elements.forEach((element) => {
    element.classList.add("ra-reveal");
    if (element.getBoundingClientRect().top < window.innerHeight * 0.94) {
      element.classList.add("ra-visible");
    } else {
      observer.observe(element);
    }
  });

  if (motionPreference && motionPreference.addEventListener) {
    motionPreference.addEventListener("change", (event) => {
      if (!event.matches) return;
      observer.disconnect();
      document.body.classList.remove("ra-motion-ready");
      document.querySelectorAll(".ra-reveal").forEach((element) => {
        element.classList.add("ra-visible");
        element.style.removeProperty("opacity");
        element.style.removeProperty("transform");
        element.style.removeProperty("filter");
      });
    });
  }
})();
