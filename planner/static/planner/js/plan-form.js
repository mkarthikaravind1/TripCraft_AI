/* Multi-step trip form: step navigation, live hints, client-side checks and loading state.
   The server re-validates everything; these checks only give faster feedback. */
(function () {
  "use strict";
  const form = document.querySelector("[data-plan-form]");
  if (!form) return;

  const steps = Array.from(form.querySelectorAll("[data-step]"));
  const stepperItems = Array.from(document.querySelectorAll("[data-stepper-item]"));
  const backBtn = form.querySelector("[data-step-back]");
  const nextBtn = form.querySelector("[data-step-next]");
  const submitBtn = form.querySelector("[data-submit]");
  const overlay = document.querySelector("[data-loading]");
  const MAX_DAYS = 14;
  let current = 0;

  // Link server-side errors to their inputs for assistive technology.
  form.querySelectorAll(".has-error").forEach((field) => {
    const error = field.querySelector(".error");
    field.querySelectorAll("input, select, textarea").forEach((input) => {
      input.setAttribute("aria-invalid", "true");
      if (error && error.id) {
        const existing = input.getAttribute("aria-describedby");
        input.setAttribute("aria-describedby", existing ? existing + " " + error.id : error.id);
      }
    });
  });

  function showStep(index, focus) {
    current = index;
    steps.forEach((step, i) => step.classList.toggle("is-active", i === index));
    stepperItems.forEach((item, i) => {
      item.classList.toggle("is-current", i === index);
      item.classList.toggle("is-done", i < index);
      if (i === index) item.setAttribute("aria-current", "step"); else item.removeAttribute("aria-current");
    });
    backBtn.hidden = index === 0;
    nextBtn.hidden = index === steps.length - 1;
    submitBtn.hidden = index !== steps.length - 1;
    if (focus) {
      const first = steps[index].querySelector("input:not([type=hidden]), select, textarea");
      if (first) first.focus({ preventScroll: true });
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function clearClientErrors(step) {
    step.querySelectorAll(".error[data-client]").forEach((el) => el.remove());
    step.querySelectorAll(".field.client-error").forEach((el) => el.classList.remove("has-error", "client-error"));
  }

  function addError(input, message) {
    const field = input.closest(".field");
    field.classList.add("has-error", "client-error");
    const p = document.createElement("p");
    p.className = "error";
    p.dataset.client = "true";
    p.textContent = message;
    field.appendChild(p);
    input.setAttribute("aria-invalid", "true");
  }

  function parseDate(value) {
    if (!value) return null;
    const [y, m, d] = value.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  function validateStep(index) {
    const step = steps[index];
    clearClientErrors(step);
    const errors = [];
    const el = (name) => form.elements[name];

    if (index === 0) {
      if (el("destination").value.trim().length < 2) errors.push([el("destination"), "Where are you going? Enter a destination."]);
      const start = parseDate(el("start_date").value);
      const end = parseDate(el("end_date").value);
      const today = new Date(); today.setHours(0, 0, 0, 0);
      if (!start) errors.push([el("start_date"), "Choose a start date."]);
      else if (start < today) errors.push([el("start_date"), "The trip can't start in the past."]);
      if (!end) errors.push([el("end_date"), "Choose a return date."]);
      else if (start && end < start) errors.push([el("end_date"), "The return date must be on or after the start date."]);
      else if (start && (end - start) / 86400000 + 1 > MAX_DAYS) errors.push([el("end_date"), "Trips can be at most " + MAX_DAYS + " days long."]);
    }
    if (index === 1) {
      const budget = parseFloat(el("budget").value);
      if (!(budget > 0)) errors.push([el("budget"), "Enter a budget greater than zero."]);
      const travellers = parseInt(el("travellers").value, 10);
      if (!(travellers >= 1 && travellers <= 20)) errors.push([el("travellers"), "Choose between 1 and 20 travellers."]);
    }
    if (index === 2) {
      const checked = form.querySelectorAll("input[name=interests]:checked").length;
      const first = form.querySelector("input[name=interests]");
      if (checked === 0) errors.push([first, "Pick at least one interest so we can personalise your plan."]);
      if (checked > 6) errors.push([first, "Choose up to 6 interests for a focused plan."]);
    }
    errors.forEach(([input, message]) => addError(input, message));
    if (errors.length) errors[0][0].focus();
    return errors.length === 0;
  }

  // Live hints: trip length and budget per person per day.
  const durationHint = form.querySelector("[data-duration]");
  const perPersonHint = form.querySelector("[data-per-person]");
  function updateHints() {
    const start = parseDate(form.elements.start_date.value);
    const end = parseDate(form.elements.end_date.value);
    let days = null;
    if (start && end && end >= start) {
      days = Math.round((end - start) / 86400000) + 1;
      durationHint.textContent = days + " day" + (days > 1 ? "s" : "") + ", " + Math.max(days - 1, 1) + " night" + (days > 2 ? "s" : "");
    } else {
      durationHint.textContent = "";
    }
    const budget = parseFloat(form.elements.budget.value);
    const travellers = parseInt(form.elements.travellers.value, 10);
    if (days && budget > 0 && travellers > 0) {
      const currency = form.elements.currency.value;
      const perDay = Math.round(budget / travellers / days);
      perPersonHint.textContent = "≈ " + perDay.toLocaleString(currency === "INR" ? "en-IN" : "en-GB") + " " + currency + " per person per day.";
    } else {
      perPersonHint.textContent = "";
    }
  }
  ["start_date", "end_date", "budget", "travellers", "currency"].forEach((name) => {
    form.elements[name].addEventListener("input", updateHints);
  });
  const startInput = form.elements.start_date;
  const endInput = form.elements.end_date;
  startInput.addEventListener("change", () => {
    endInput.min = startInput.value;
    if (endInput.value && endInput.value < startInput.value) endInput.value = startInput.value;
    updateHints();
  });
  const todayIso = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  startInput.min = todayIso;
  endInput.min = startInput.value || todayIso;
  updateHints();

  // Enforce the six-interest maximum as the user clicks.
  form.querySelectorAll("input[name=interests]").forEach((box) => {
    box.addEventListener("change", () => {
      const checked = form.querySelectorAll("input[name=interests]:checked");
      if (checked.length > 6) {
        box.checked = false;
        addError(box, "Choose up to 6 interests for a focused plan.");
      } else {
        clearClientErrors(steps[2]);
      }
    });
  });

  nextBtn.addEventListener("click", () => {
    if (validateStep(current)) showStep(current + 1, true);
  });
  backBtn.addEventListener("click", () => showStep(current - 1, true));
  form.addEventListener("keydown", (event) => {
    // Enter in a text field moves to the next step instead of submitting early.
    if (event.key === "Enter" && event.target.tagName === "INPUT" && current < steps.length - 1) {
      event.preventDefault();
      nextBtn.click();
    }
  });

  // Submit with a visible, accessible loading state.
  let submitting = false;
  form.addEventListener("submit", (event) => {
    if (submitting) { event.preventDefault(); return; }
    for (let i = 0; i < steps.length; i++) {
      if (!validateStep(i)) {
        event.preventDefault();
        showStep(i, false);
        validateStep(i);
        return;
      }
    }
    submitting = true;
    submitBtn.disabled = true;
    submitBtn.classList.add("is-loading");
    submitBtn.textContent = "Generating…";
    startLoading();
  });

  function startLoading() {
    if (!overlay) return;
    overlay.hidden = false;
    const items = overlay.querySelectorAll(".loading-steps li");
    const label = overlay.querySelector("[data-loading-step]");
    let i = 0;
    const advance = () => {
      items.forEach((li, k) => {
        li.classList.toggle("is-done", k < i);
        li.classList.toggle("is-active", k === i);
      });
      if (label && items[i]) label.textContent = items[i].textContent + "…";
      if (i < items.length - 1) { i++; setTimeout(advance, 5000 + i * 2500); }
    };
    advance();
  }

  // If the browser restores this page from the back/forward cache, reset the button.
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      submitting = false;
      submitBtn.disabled = false;
      submitBtn.classList.remove("is-loading");
      submitBtn.textContent = "Generate my itinerary";
      if (overlay) overlay.hidden = true;
    }
  });

  // Start on the first step that has a server-side error, if any.
  const firstErrorStep = steps.findIndex((step) => step.querySelector(".has-error"));
  showStep(firstErrorStep >= 0 ? firstErrorStep : 0, false);
})();
