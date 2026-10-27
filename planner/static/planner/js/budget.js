/* Smart Budget Optimiser — browser copy of planner/services/budget.py.
   Integer minor units ("cents") throughout; percentages round half up.
   Keep this file and budget.py in step: the tests compare their outputs. */
(function (root) {
  "use strict";

  function applyPercent(amount, percent) {
    return Math.floor((amount * percent + 50) / 100);
  }

  function divideRound(amount, divisor) {
    return Math.floor((amount + Math.floor(divisor / 2)) / divisor);
  }

  function compute(inputs) {
    const travellers = Math.max(parseInt(inputs.travellers, 10), 1);
    const days = inputs.days;
    const numDays = Math.max(days.length, 1);
    const expenses = inputs.expenses;

    const expenseAmount = (key, percent) => {
      const item = expenses[key];
      if (item.user_cents !== null && item.user_cents !== undefined) return item.user_cents;
      return applyPercent(item.estimate_cents, percent === undefined ? 100 : percent);
    };

    const daily = days.map((day) => {
      const perPerson = day.activities.filter((a) => !a.removed).reduce((sum, a) => sum + a.cost_cents_pp, 0);
      return {
        day_number: day.day_number,
        activities: travellers * perPerson,
        food: applyPercent(day.meal_cents_pp * travellers, inputs.meal_percent),
      };
    });

    const categories = {
      transport: expenseAmount("transport"),
      accommodation: expenseAmount("accommodation", inputs.stay_percent),
      food: daily.reduce((s, d) => s + d.food, 0),
      activities: daily.reduce((s, d) => s + d.activities, 0),
      misc: expenseAmount("misc"),
    };
    const subtotal = categories.transport + categories.accommodation + categories.food + categories.activities + categories.misc;
    categories.contingency = applyPercent(subtotal, inputs.contingency_percent);
    const total = subtotal + categories.contingency;

    const shared = categories.transport + categories.accommodation + categories.misc + categories.contingency;
    const perDayShared = Math.floor(shared / numDays);
    daily.forEach((day, index) => {
      day.shared = perDayShared + (index === daily.length - 1 ? shared - perDayShared * numDays : 0);
      day.total = day.activities + day.food + day.shared;
    });

    const budget = inputs.budget_cents;
    const utilisationTenths = budget > 0 ? divideRound(total * 1000, budget) : 0;
    return {
      categories: categories,
      total: total,
      budget: budget,
      remaining: budget - total,
      over_budget: total > budget,
      utilisation: utilisationTenths / 10,
      per_traveller: divideRound(total, travellers),
      per_day: divideRound(total, numDays),
      daily: daily,
    };
  }

  function baselineInputs(inputs) {
    const expenses = {};
    Object.keys(inputs.expenses).forEach((key) => {
      expenses[key] = Object.assign({}, inputs.expenses[key], { user_cents: null });
    });
    return Object.assign({}, inputs, {
      meal_percent: 100,
      stay_percent: 100,
      days: inputs.days.map((day) => Object.assign({}, day, {
        activities: day.activities.map((a) => Object.assign({}, a, { removed: false })),
      })),
      expenses: expenses,
    });
  }

  function summarise(inputs) {
    const result = compute(inputs);
    const baseline = compute(baselineInputs(inputs));
    result.baseline_total = baseline.total;
    result.savings = baseline.total - result.total;
    return result;
  }

  function groupDigits(n, currency) {
    const digits = String(n);
    if (currency !== "INR" || digits.length <= 3) return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    let head = digits.slice(0, -3);
    const tail = digits.slice(-3);
    const parts = [];
    while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
    if (head) parts.unshift(head);
    return parts.join(",") + "," + tail;
  }

  /* Format integer cents exactly like the Django `money` filter. */
  function formatCents(cents, currency, symbol) {
    const whole = divideRound(Math.abs(cents), 100);
    const sign = cents < 0 && whole ? "−" : "";
    return sign + symbol + groupDigits(whole, currency);
  }

  const api = { compute: compute, summarise: summarise, baselineInputs: baselineInputs, applyPercent: applyPercent, formatCents: formatCents };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TripBudget = api;
})(typeof window !== "undefined" ? window : globalThis);
