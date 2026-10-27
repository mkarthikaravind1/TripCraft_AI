/* Help centre: live search and topic filters over the database-rendered FAQs. */
(function () {
  "use strict";
  const search = document.querySelector("[data-faq-search]");
  const items = Array.from(document.querySelectorAll(".faq-item"));
  const filters = Array.from(document.querySelectorAll("[data-faq-filter]"));
  const empty = document.querySelector("[data-faq-empty]");
  const count = document.querySelector("[data-faq-count]");
  if (!search || !items.length) return;
  let category = "";

  function apply() {
    const terms = search.value.toLowerCase().split(/\s+/).filter(Boolean);
    let visible = 0;
    items.forEach((item) => {
      const text = item.textContent.toLowerCase();
      const show = (!category || item.dataset.category === category) && terms.every((t) => text.includes(t));
      item.hidden = !show;
      if (show) visible++;
    });
    empty.hidden = visible > 0;
    count.textContent = visible + (visible === 1 ? " question" : " questions");
  }

  search.addEventListener("input", apply);
  filters.forEach((btn) => btn.addEventListener("click", () => {
    category = btn.dataset.faqFilter;
    filters.forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
    apply();
  }));

  // Open an FAQ linked from the assistant (e.g. /faq/#faq-3).
  function openFromHash() {
    const target = location.hash && document.querySelector(location.hash);
    if (target && target.tagName === "DETAILS") {
      target.hidden = false;
      target.open = true;
    }
  }
  window.addEventListener("hashchange", openFromHash);
  openFromHash();
})();
