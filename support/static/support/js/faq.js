/* Help centre: loads FAQs from the SQL-backed JSON API (/api/faqs/), then offers
   live search and topic filters. Rendering uses textContent, never innerHTML. */
(function () {
  "use strict";
  const list = document.querySelector("[data-faq-list]");
  if (!list) return;
  const search = document.querySelector("[data-faq-search]");
  const filterBar = document.querySelector("[data-faq-filters]");
  const empty = document.querySelector("[data-faq-empty]");
  const count = document.querySelector("[data-faq-count]");
  const errorBox = document.querySelector("[data-faq-error]");
  let items = [];
  let category = "";

  function chevron() {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "icon chev");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#i-chev");
    svg.appendChild(use);
    return svg;
  }

  function renderFaq(faq) {
    const details = document.createElement("details");
    details.className = "faq-item";
    details.id = "faq-" + faq.id;
    details.dataset.category = faq.category;
    const summary = document.createElement("summary");
    const q = document.createElement("span");
    q.textContent = faq.question;
    summary.append(q, chevron());
    const body = document.createElement("div");
    body.className = "faq-answer";
    const a = document.createElement("p");
    a.textContent = faq.answer;
    const meta = document.createElement("p");
    meta.className = "faq-meta small muted";
    meta.textContent = faq.category_label;
    body.append(a, meta);
    details.append(summary, body);
    return details;
  }

  function renderFilters(categories) {
    filterBar.querySelectorAll("[data-faq-filter]:not([data-faq-filter=''])").forEach((b) => b.remove());
    categories.forEach((c) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "filter-chip";
      btn.setAttribute("aria-pressed", "false");
      btn.dataset.faqFilter = c.value;
      btn.textContent = c.label;
      filterBar.appendChild(btn);
    });
  }

  function apply() {
    const terms = search.value.toLowerCase().split(/\s+/).filter(Boolean);
    let visible = 0;
    items.forEach((item) => {
      const text = item.textContent.toLowerCase();
      const show = (!category || item.dataset.category === category) && terms.every((t) => text.includes(t));
      item.hidden = !show;
      if (show) visible++;
    });
    empty.hidden = visible > 0 || !items.length;
    count.textContent = visible + (visible === 1 ? " question" : " questions");
  }

  function openFromHash() {
    const target = location.hash && document.getElementById(location.hash.slice(1));
    if (target && target.tagName === "DETAILS") {
      target.hidden = false;
      target.open = true;
      target.scrollIntoView({ block: "center" });
    }
  }

  async function load() {
    errorBox.hidden = true;
    list.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(list.dataset.faqApi, { headers: { Accept: "application/json" }, credentials: "same-origin" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      list.replaceChildren(...data.faqs.map(renderFaq));
      items = Array.from(list.querySelectorAll(".faq-item"));
      renderFilters(data.categories);
      if (!items.length) count.textContent = "No FAQs are available right now.";
      apply();
      openFromHash();
    } catch (e) {
      list.replaceChildren();
      count.textContent = "";
      errorBox.hidden = false;
    } finally {
      list.setAttribute("aria-busy", "false");
    }
  }

  search.addEventListener("input", apply);
  filterBar.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-faq-filter]");
    if (!btn) return;
    category = btn.dataset.faqFilter;
    filterBar.querySelectorAll("[data-faq-filter]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
    apply();
  });
  document.querySelector("[data-faq-retry]").addEventListener("click", load);
  window.addEventListener("hashchange", openFromHash);
  load();
})();
