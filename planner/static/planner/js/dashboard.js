/* Interactive travel dashboard: day tabs, activity cards, live budget, charts.
   Every change is recalculated instantly in the browser with TripBudget and then
   saved through a fetch() call; the server's recalculated result is authoritative. */
(function () {
  "use strict";
  const root = document.querySelector("[data-dashboard]");
  const stateEl = document.getElementById("budget-state");
  if (!root || !stateEl || !window.TripBudget) return;

  const state = JSON.parse(stateEl.textContent);
  const money = (cents) => window.TripBudget.formatCents(cents, state.currency, state.symbol);
  const css = getComputedStyle(document.documentElement);
  const colour = (name) => css.getPropertyValue(name).trim();
  const CAT_COLOURS = state.order.map((key) => colour("--cat-" + key));
  const saveStatus = root.querySelector("[data-save-status]");

  // ---------------------------------------------------------------- tabs
  const tabs = Array.from(root.querySelectorAll("[role=tab]"));
  function selectTab(tab, focus) {
    tabs.forEach((t) => {
      const selected = t === tab;
      t.setAttribute("aria-selected", String(selected));
      t.tabIndex = selected ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !selected;
    });
    if (focus) tab.focus();
    tab.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => selectTab(tab, false));
    tab.addEventListener("keydown", (event) => {
      let next = null;
      if (event.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
      if (event.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
      if (event.key === "Home") next = tabs[0];
      if (event.key === "End") next = tabs[tabs.length - 1];
      if (next) { event.preventDefault(); selectTab(next, true); }
    });
  });

  // ------------------------------------------------------ expand/collapse
  root.querySelectorAll(".activity-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      document.getElementById(btn.getAttribute("aria-controls")).hidden = !open;
    });
  });

  // -------------------------------------------------------------- saving
  const csrf = window.TripCraft.getCookie("csrftoken");
  let latestRequest = 0;
  let pending = 0;

  function setStatus(text, isError) {
    if (!saveStatus) return;
    saveStatus.textContent = text;
    saveStatus.classList.toggle("is-error", Boolean(isError));
  }

  async function post(url, body) {
    const id = ++latestRequest;
    pending++;
    setStatus("Saving…");
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        credentials: "same-origin",
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) throw new Error(data.error || "Could not save your change.");
      if (id === latestRequest) {
        state.inputs = data.inputs;
        render(data.result);
      }
      setStatus("All changes saved.");
      return data;
    } catch (error) {
      setStatus((error && error.message ? error.message : "Network error") + " Please try again.", true);
      throw error;
    } finally {
      pending--;
    }
  }

  function findActivity(id) {
    for (const day of state.inputs.days) {
      const activity = day.activities.find((a) => a.id === id);
      if (activity) return activity;
    }
    return null;
  }

  function recalcLocal() {
    render(window.TripBudget.summarise(state.inputs));
  }

  // --------------------------------------------------- activity actions
  function setRemovedUI(li, removed) {
    li.classList.toggle("is-removed", removed);
    const btn = li.querySelector("[data-action=remove]");
    const name = li.querySelector(".activity-name").textContent;
    btn.setAttribute("aria-label", (removed ? "Restore “" : "Remove “") + name + "”");
    btn.title = removed ? "Restore" : "Remove from plan";
    btn.querySelector("use").setAttribute("href", removed ? "#i-undo" : "#i-trash");
    const note = li.querySelector(".removed-note");
    if (note) note.hidden = !removed;
  }

  root.querySelectorAll("[data-activity]").forEach((li) => {
    const id = parseInt(li.dataset.activity, 10);
    const url = root.dataset.activityUrl + id + "/";

    li.querySelector("[data-action=complete]").addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      const done = btn.getAttribute("aria-pressed") !== "true";
      btn.setAttribute("aria-pressed", String(done));
      li.classList.toggle("is-completed", done);
      try { await post(url, { completed: done }); } catch (e) {
        btn.setAttribute("aria-pressed", String(!done));
        li.classList.toggle("is-completed", !done);
      }
    });

    li.querySelector("[data-action=remove]").addEventListener("click", async () => {
      const activity = findActivity(id);
      if (!activity) return;
      const removed = !activity.removed;
      activity.removed = removed;
      setRemovedUI(li, removed);
      recalcLocal();
      try { await post(url, { removed: removed }); } catch (e) {
        activity.removed = !removed;
        setRemovedUI(li, !removed);
        recalcLocal();
      }
    });
  });

  // --------------------------------------------------- budget settings
  const adjust = root.querySelector("[data-adjust]");
  const budgetUrl = root.dataset.budgetUrl;
  const debounceTimers = {};
  function debounce(key, fn, wait) {
    clearTimeout(debounceTimers[key]);
    debounceTimers[key] = setTimeout(fn, wait);
  }

  adjust.querySelector("[data-setting=meal_style]").addEventListener("change", (event) => {
    state.inputs.meal_percent = state.meal_styles[event.target.value];
    recalcLocal();
    post(budgetUrl, { meal_style: event.target.value }).catch(() => {});
  });
  adjust.querySelector("[data-setting=stay_style]").addEventListener("change", (event) => {
    state.inputs.stay_percent = state.stay_styles[event.target.value];
    recalcLocal();
    post(budgetUrl, { stay_style: event.target.value }).catch(() => {});
  });

  const contingency = adjust.querySelector("[data-setting=contingency_percent]");
  const contingencyOut = adjust.querySelector("[data-contingency-out]");
  contingency.addEventListener("input", () => {
    const value = parseInt(contingency.value, 10);
    contingencyOut.textContent = value + "%";
    state.inputs.contingency_percent = value;
    recalcLocal();
    debounce("contingency", () => post(budgetUrl, { contingency_percent: value }).catch(() => {}), 400);
  });

  adjust.querySelectorAll("[data-amount]").forEach((input) => {
    const key = input.dataset.amount;
    const resetBtn = adjust.querySelector("[data-reset=" + key + "]");
    const sourceCell = root.querySelector("[data-source=" + key + "]");
    const estimateLabel = sourceCell ? sourceCell.textContent : "";

    input.addEventListener("input", () => {
      const value = parseFloat(input.value);
      if (!(value >= 0)) return;
      state.inputs.expenses[key].user_cents = Math.round(value * 100);
      if (sourceCell) sourceCell.textContent = "Your figure";
      resetBtn.hidden = false;
      recalcLocal();
      debounce(key, () => post(budgetUrl, { [key + "_amount"]: value.toFixed(2) }).catch(() => {}), 600);
    });

    resetBtn.addEventListener("click", () => {
      clearTimeout(debounceTimers[key]);
      const item = state.inputs.expenses[key];
      item.user_cents = null;
      input.value = Math.round(item.estimate_cents / 100);
      if (sourceCell) sourceCell.textContent = estimateLabel === "Your figure" ? sourceLabelDefault() : estimateLabel;
      resetBtn.hidden = true;
      recalcLocal();
      post(budgetUrl, { ["reset_" + key]: true }).catch(() => {});
    });
  });
  function sourceLabelDefault() {
    const tag = root.querySelector(".tag-ai");
    return tag ? "AI estimate" : "Sample estimate";
  }

  // ------------------------------------------------ trim paid activities
  const trim = adjust.querySelector("[data-trim]");
  const trimOut = adjust.querySelector("[data-trim-out]");
  const trimPreview = adjust.querySelector("[data-trim-preview]");
  const trimApply = adjust.querySelector("[data-trim-apply]");
  let trimCandidates = [];

  function maxActivityCost() {
    let max = 0;
    state.inputs.days.forEach((d) => d.activities.forEach((a) => { if (!a.removed) max = Math.max(max, a.cost_cents_pp); }));
    return max;
  }
  function setupTrim() {
    const max = maxActivityCost();
    trim.disabled = max === 0;
    trim.max = String(Math.max(max, 1));
    trim.step = String(Math.max(Math.round(max / 50), 1));
    if (parseInt(trim.value, 10) > max || trim.dataset.untouched !== "false") trim.value = trim.max;
    updateTrim();
  }
  function updateTrim() {
    const threshold = parseInt(trim.value, 10);
    trimOut.textContent = money(threshold);
    trimCandidates = [];
    state.inputs.days.forEach((d) => d.activities.forEach((a) => {
      if (!a.removed && a.cost_cents_pp > threshold) trimCandidates.push(a.id);
    }));
    if (!trimCandidates.length) {
      trimPreview.textContent = trim.disabled ? "No paid activities left to trim." : "No activities above this amount. Move the slider left to preview savings.";
      trimApply.disabled = true;
      return;
    }
    const preview = JSON.parse(JSON.stringify(state.inputs));
    preview.days.forEach((d) => d.activities.forEach((a) => { if (trimCandidates.includes(a.id)) a.removed = true; }));
    const current = window.TripBudget.compute(state.inputs);
    const after = window.TripBudget.compute(preview);
    const names = trimCandidates.map((id) => {
      const li = root.querySelector('[data-activity="' + id + '"] .activity-name');
      return li ? li.textContent : "";
    }).filter(Boolean);
    trimPreview.textContent = "Removes " + trimCandidates.length + " activit" + (trimCandidates.length === 1 ? "y" : "ies") +
      " (" + names.slice(0, 3).join(", ") + (names.length > 3 ? "…" : "") + "), saving " + money(current.total - after.total) +
      ". New total " + money(after.total) + (after.over_budget ? " — still over budget." : ", leaving " + money(after.remaining) + ".");
    trimApply.disabled = false;
  }
  trim.addEventListener("input", () => { trim.dataset.untouched = "false"; updateTrim(); });
  trimApply.addEventListener("click", async () => {
    const ids = trimCandidates.slice();
    if (!ids.length) return;
    trimApply.disabled = true;
    ids.forEach((id) => {
      const activity = findActivity(id);
      if (activity) activity.removed = true;
      const li = root.querySelector('[data-activity="' + id + '"]');
      if (li) setRemovedUI(li, true);
    });
    recalcLocal();
    try { await post(root.dataset.removeUrl, { ids: ids }); } catch (e) {
      ids.forEach((id) => {
        const activity = findActivity(id);
        if (activity) activity.removed = false;
        const li = root.querySelector('[data-activity="' + id + '"]');
        if (li) setRemovedUI(li, false);
      });
      recalcLocal();
    }
  });

  // --------------------------------------------------------------- charts
  let categoryChart = null;
  let dailyChart = null;
  function initCharts(result) {
    const doughnutCanvas = document.getElementById("category-chart");
    const barCanvas = document.getElementById("daily-chart");
    if (typeof window.Chart === "undefined") {
      [doughnutCanvas, barCanvas].forEach((canvas) => {
        if (canvas) canvas.parentElement.innerHTML = '<p class="chart-fallback">Charts could not load. The table shows the same figures.</p>';
      });
      return;
    }
    const Chart = window.Chart;
    Chart.defaults.font.family = css.getPropertyValue("--font-body");
    Chart.defaults.color = colour("--muted");
    const tooltip = { callbacks: { label: (ctx) => " " + ctx.dataset.label + ": " + money(ctx.raw) } };
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    categoryChart = new Chart(doughnutCanvas, {
      type: "doughnut",
      data: {
        labels: state.order.map((k) => state.labels[k]),
        datasets: [{ label: "Estimated cost", data: state.order.map((k) => result.categories[k]), backgroundColor: CAT_COLOURS, borderColor: "#fff", borderWidth: 2, hoverOffset: 6 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: "64%", animation: reduced ? false : { duration: 500 },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => " " + ctx.label + ": " + money(ctx.raw) } },
        },
      },
    });

    dailyChart = new Chart(barCanvas, {
      type: "bar",
      data: {
        labels: result.daily.map((d) => "Day " + d.day_number),
        datasets: [
          { label: "Activities", data: result.daily.map((d) => d.activities), backgroundColor: colour("--cat-activities"), borderRadius: 4 },
          { label: "Food", data: result.daily.map((d) => d.food), backgroundColor: colour("--cat-food"), borderRadius: 4 },
          { label: "Stay, travel & extras", data: result.daily.map((d) => d.shared), backgroundColor: colour("--cat-accommodation"), borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: reduced ? false : { duration: 400 },
        scales: {
          x: { stacked: true, grid: { display: false } },
          y: { stacked: true, beginAtZero: true, ticks: { callback: (v) => money(v), maxTicksLimit: 5 }, grid: { color: colour("--border") } },
        },
        plugins: { legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } }, tooltip: tooltip },
      },
    });
  }

  // --------------------------------------------------------------- render
  function setAll(selector, text) {
    root.querySelectorAll(selector).forEach((el) => { el.textContent = text; });
  }

  function render(result) {
    setAll("[data-stat=total]", money(result.total));
    setAll("[data-stat=remaining]", money(Math.abs(result.remaining)));
    setAll("[data-stat=savings]", money(result.savings));
    setAll("[data-stat=per_traveller]", money(result.per_traveller));
    setAll("[data-stat=per_day]", money(result.per_day));
    setAll("[data-stat=utilisation]", String(result.utilisation));
    setAll("[data-remaining-label]", result.over_budget ? "Over budget by" : "Remaining budget");
    state.order.forEach((key) => setAll('[data-cat="' + key + '"]', money(result.categories[key])));

    result.daily.forEach((d) => {
      setAll('[data-day-total="' + d.day_number + '"]', money(d.total));
      setAll('[data-day-cost="' + d.day_number + '"]', money(d.total));
      setAll('[data-day-activities="' + d.day_number + '"]', money(d.activities));
      setAll('[data-day-food="' + d.day_number + '"]', money(d.food));
      setAll('[data-day-shared="' + d.day_number + '"]', money(d.shared));
    });

    const meter = root.querySelector("[data-meter]");
    meter.querySelector("span").style.width = Math.min(result.utilisation, 100) + "%";
    meter.setAttribute("aria-valuenow", String(result.utilisation));
    meter.classList.toggle("is-over", result.over_budget);
    meter.classList.toggle("is-warn", !result.over_budget && result.utilisation >= 90);
    root.querySelector("[data-remaining-card]").classList.toggle("is-over", result.over_budget);
    root.querySelector("[data-over-budget]").hidden = !result.over_budget;
    root.querySelector(".adjust-result").classList.toggle("is-over", result.over_budget);

    if (categoryChart) {
      categoryChart.data.datasets[0].data = state.order.map((k) => result.categories[k]);
      categoryChart.update();
    }
    if (dailyChart) {
      dailyChart.data.datasets[0].data = result.daily.map((d) => d.activities);
      dailyChart.data.datasets[1].data = result.daily.map((d) => d.food);
      dailyChart.data.datasets[2].data = result.daily.map((d) => d.shared);
      dailyChart.update();
    }
    setupTrim();
  }

  // ---------------------------------------------------------------- misc
  const printBtn = root.querySelector("[data-print]");
  if (printBtn) printBtn.addEventListener("click", () => window.print());

  const regenForm = root.querySelector("[data-regenerate-form]");
  const overlay = document.querySelector("[data-loading]");
  if (regenForm) {
    regenForm.addEventListener("submit", (event) => {
      if (!window.confirm("Generate a new itinerary? Your current activities and budget changes for this trip will be replaced.")) {
        event.preventDefault();
        return;
      }
      regenForm.querySelector("button").disabled = true;
      if (overlay) overlay.hidden = false;
    });
  }
  window.addEventListener("pageshow", (event) => {
    if (event.persisted && overlay) {
      overlay.hidden = true;
      if (regenForm) regenForm.querySelector("button").disabled = false;
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (pending > 0) { event.preventDefault(); event.returnValue = ""; }
  });

  // -------------------------------------------------------------- weather
  // Loaded after the page renders so a slow weather service never blocks the dashboard.
  async function loadWeather() {
    const card = root.querySelector("[data-weather]");
    if (!card) return;
    const statusEl = card.querySelector("[data-weather-status]");
    const list = card.querySelector("[data-weather-days]");
    const sourceEl = card.querySelector("[data-weather-source]");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(card.dataset.weatherUrl, { credentials: "same-origin", signal: controller.signal });
      const data = await response.json();
      if (!data.days || !data.days.length) {
        statusEl.textContent = data.message || "Weather information is unavailable.";
        return;
      }
      statusEl.textContent = (data.location ? data.location + ". " : "") + (data.message || "");
      list.innerHTML = "";
      data.days.forEach((day) => {
        const li = document.createElement("li");
        const date = new Date(day.date + "T00:00:00");
        const label = document.createElement("span");
        label.className = "weather-date";
        label.textContent = date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
        const summary = document.createElement("span");
        summary.textContent = day.summary;
        const temps = document.createElement("span");
        temps.className = "weather-temp";
        temps.textContent = day.temp_max + "° / " + day.temp_min + "°C" + (day.rain_chance !== null ? " · " + day.rain_chance + "% rain" : "");
        li.append(label, summary, temps);
        list.appendChild(li);
      });
      list.hidden = false;
      if (data.fetched_at) {
        sourceEl.textContent = "Forecast from Open-Meteo, fetched " + new Date(data.fetched_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) + ". Forecasts change — check again before you travel.";
        sourceEl.hidden = false;
      }
    } catch (error) {
      statusEl.textContent = "Weather information is temporarily unavailable. Your itinerary is unaffected.";
    } finally {
      clearTimeout(timer);
    }
  }

  initCharts(state.result);
  render(state.result);
  loadWeather();
})();
