/* Site-wide behaviour: navigation, reveal-on-scroll, image fallbacks, small helpers. */
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  // Mobile navigation toggle.
  const toggle = document.querySelector("[data-nav-toggle]");
  const menu = document.getElementById("nav-menu");
  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      menu.classList.toggle("is-open", open);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menu.classList.contains("is-open")) {
        toggle.setAttribute("aria-expanded", "false");
        menu.classList.remove("is-open");
        toggle.focus();
      }
    });
  }

  // Header shadow once the page scrolls.
  const header = document.querySelector("[data-header]");
  if (header) {
    const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 8);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // Gentle reveal-on-scroll (skipped automatically for reduced motion via CSS).
  const revealItems = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && revealItems.length) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { rootMargin: "0px 0px -40px 0px", threshold: 0.05 });
    revealItems.forEach((el) => observer.observe(el));
  } else {
    revealItems.forEach((el) => el.classList.add("is-visible"));
  }

  // If a photo fails to load, hide it so its tinted frame shows instead.
  document.querySelectorAll("img[data-fallback]").forEach((img) => {
    const hide = () => { img.style.visibility = "hidden"; };
    if (img.complete && img.naturalWidth === 0) hide();
    img.addEventListener("error", hide);
  });

  // Confirmation for destructive forms.
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  // Shared helpers for other scripts.
  window.TripCraft = window.TripCraft || {};
  window.TripCraft.getCookie = function (name) {
    const match = document.cookie.split(";").map((c) => c.trim()).find((c) => c.startsWith(name + "="));
    return match ? decodeURIComponent(match.slice(name.length + 1)) : "";
  };
})();
