/* TripCraft floating assistant. All answers come from the Django backend
   (/support/chat/), which retrieves FAQs and error codes and calls the AI. */
(function () {
  "use strict";
  const root = document.querySelector("[data-chat]");
  if (!root) return;

  const toggle = root.querySelector("[data-chat-toggle]");
  const panel = root.querySelector("#chat-panel");
  const closeBtn = root.querySelector("[data-chat-close]");
  const log = root.querySelector("[data-chat-log]");
  const form = root.querySelector("[data-chat-form]");
  const input = root.querySelector("[data-chat-input]");
  const sendBtn = root.querySelector("[data-chat-send]");
  const ticketForm = root.querySelector("[data-chat-ticket]");
  const ticketError = root.querySelector("[data-ticket-error]");
  const suggestions = root.querySelector("[data-chat-suggestions]");
  const faqUrl = root.dataset.faqUrl;
  let busy = false;
  let restored = false;
  let lastUserMessage = "";

  function csrfToken() {
    const match = document.cookie.split(";").map((c) => c.trim()).find((c) => c.startsWith("csrftoken="));
    return match ? decodeURIComponent(match.split("=")[1]) : "";
  }

  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(body),
    });
    let data = {};
    try { data = await response.json(); } catch (e) { /* non-JSON error */ }
    return { status: response.status, data: data };
  }

  // ------------------------------------------------------------ open/close
  function open(focusInput) {
    panel.hidden = false;
    root.classList.add("is-open");
    toggle.setAttribute("aria-expanded", "true");
    if (!restored) restoreHistory();
    scrollToEnd();
    if (focusInput !== false) input.focus();
  }
  function close() {
    panel.hidden = true;
    root.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.focus();
  }
  toggle.addEventListener("click", () => (panel.hidden ? open() : close()));
  closeBtn.addEventListener("click", close);
  panel.addEventListener("keydown", (event) => { if (event.key === "Escape") { event.stopPropagation(); close(); } });

  document.querySelectorAll("[data-open-chat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      open();
      const prefill = btn.dataset.chatPrefill;
      if (prefill) send(prefill);
    });
  });

  async function restoreHistory() {
    restored = true;
    try {
      const response = await fetch(root.dataset.stateEndpoint, { credentials: "same-origin", headers: { "Accept": "application/json" } });
      const data = await response.json();
      if (data.history && data.history.length) {
        if (suggestions) suggestions.hidden = true;
        const earlier = document.createElement("p");
        earlier.className = "msg-note";
        earlier.textContent = "Earlier in this conversation";
        log.insertBefore(earlier, suggestions ? suggestions.nextSibling : null);
        data.history.forEach((turn) => addBubble(turn.role === "user" ? "user" : "assistant", turn.text));
        lastUserMessage = data.last_problem || lastUserMessage;
        scrollToEnd();
      }
    } catch (e) { /* history restore is a convenience only */ }
  }

  // --------------------------------------------------------------- render
  function scrollToEnd() { log.scrollTop = log.scrollHeight; }

  function addBubble(role, text, extraClass) {
    const wrap = document.createElement("div");
    wrap.className = "msg msg-" + role + (extraClass ? " " + extraClass : "");
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    String(text).split(/\n{2,}|\n/).forEach((para) => {
      if (!para.trim()) return;
      const p = document.createElement("p");
      p.textContent = para;
      bubble.appendChild(p);
    });
    wrap.appendChild(bubble);
    log.appendChild(wrap);
    scrollToEnd();
    return wrap;
  }

  function addTyping() {
    const wrap = document.createElement("div");
    wrap.className = "msg msg-assistant";
    wrap.setAttribute("aria-label", "Assistant is typing");
    wrap.innerHTML = '<div class="bubble typing"><span></span><span></span><span></span></div>';
    log.appendChild(wrap);
    scrollToEnd();
    return wrap;
  }

  function icon(path) {
    return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="' + path + '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }
  const THUMB_UP = "M7 11v9H4.5v-9H7Zm0 0 4-7a2 2 0 0 1 2.5 2.3L13 10h5.2a2 2 0 0 1 2 2.4l-1.3 6A2 2 0 0 1 17 20H7";
  const THUMB_DOWN = "M7 13V4H4.5v9H7Zm0 0 4 7a2 2 0 0 0 2.5-2.3L13 14h5.2a2 2 0 0 0 2-2.4l-1.3-6A2 2 0 0 0 17 4H7";

  function renderReply(data) {
    const reply = data.reply;
    const wrap = addBubble("assistant", reply.text);

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const badge = document.createElement("span");
    badge.className = "msg-badge";
    badge.textContent = reply.ai_used ? "AI-assisted" : "Help centre";
    badge.title = reply.ai_used ? "Written by Gemini using TripCraft help information" : "Taken directly from the TripCraft help centre";
    meta.appendChild(badge);
    if (!data.logged) {
      const notLogged = document.createElement("span");
      notLogged.textContent = "Not saved to chat history";
      meta.appendChild(notLogged);
    }
    wrap.appendChild(meta);

    if (reply.note) {
      const note = document.createElement("p");
      note.className = "msg-note";
      note.textContent = reply.note;
      wrap.appendChild(note);
    }

    if (reply.sources && reply.sources.length) {
      const sources = document.createElement("div");
      sources.className = "msg-sources";
      reply.sources.slice(0, 3).forEach((s) => {
        const a = document.createElement("a");
        a.href = faqUrl + (s.type === "faq" ? "#faq-" + s.id : "#error-" + s.code);
        a.textContent = (s.type === "faq" ? "FAQ: " : "") + s.label;
        sources.appendChild(a);
      });
      wrap.appendChild(sources);
    }

    const actions = document.createElement("div");
    actions.className = "msg-actions";
    if (reply.offer_ticket) {
      const offer = document.createElement("button");
      offer.type = "button";
      offer.className = "ticket-offer";
      offer.textContent = "Create a support ticket";
      offer.addEventListener("click", () => showTicketForm(reply));
      actions.appendChild(offer);
    }
    if (reply.kind !== "greeting" && reply.kind !== "ticket_prompt") {
      actions.appendChild(feedbackControls(data.message_id));
    }
    if (actions.childNodes.length) wrap.appendChild(actions);
    if (reply.kind === "ticket_prompt") showTicketForm(reply);
    scrollToEnd();
  }

  function feedbackControls(messageId) {
    const group = document.createElement("span");
    group.className = "msg-actions";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", "Was this helpful?");
    const status = document.createElement("span");
    status.className = "feedback-status";
    status.setAttribute("aria-live", "polite");
    [["up", "Helpful", THUMB_UP], ["down", "Not helpful", THUMB_DOWN]].forEach(([rating, label, path]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "feedback-btn";
      btn.setAttribute("aria-label", label);
      btn.setAttribute("aria-pressed", "false");
      btn.title = label;
      btn.innerHTML = icon(path);
      btn.addEventListener("click", async () => {
        group.querySelectorAll("button").forEach((b) => { b.disabled = true; });
        btn.setAttribute("aria-pressed", "true");
        try {
          const { data } = await postJSON(root.dataset.feedbackEndpoint, { rating: rating, message_id: messageId || "" });
          status.textContent = data.message || (data.saved ? "Thanks!" : "Feedback couldn't be recorded.");
        } catch (e) {
          status.textContent = "Feedback couldn't be sent.";
        }
      });
      group.appendChild(btn);
    });
    group.appendChild(status);
    return group;
  }

  // ---------------------------------------------------------------- send
  async function send(text) {
    const message = (text || "").trim();
    if (!message || busy) return;
    if (message.length > 1000) {
      addBubble("assistant", "Please keep messages under 1,000 characters.", "msg-error");
      return;
    }
    busy = true;
    sendBtn.disabled = true;
    if (suggestions) suggestions.hidden = true;
    addBubble("user", message);
    lastUserMessage = message;
    input.value = "";
    autosize();
    const typing = addTyping();
    try {
      const { status, data } = await postJSON(root.dataset.endpoint, { message: message });
      typing.remove();
      if (status === 200 && data.ok) {
        renderReply(data);
      } else if (status === 429) {
        addBubble("assistant", (data.error || "You're sending messages quickly.") + " (Error 429)", "msg-error");
      } else {
        addBubble("assistant", (data.error || "Sorry, something went wrong.") + (data.code ? " (Error " + data.code + ")" : ""), "msg-error");
      }
    } catch (e) {
      typing.remove();
      addBubble("assistant", "I couldn't reach TripCraft. Check your connection and try again.", "msg-error");
    } finally {
      busy = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", (event) => { event.preventDefault(); send(input.value); });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send(input.value);
    }
  });
  function autosize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  }
  input.addEventListener("input", autosize);
  root.querySelectorAll("[data-suggest]").forEach((btn) => btn.addEventListener("click", () => send(btn.textContent)));

  // --------------------------------------------------------------- tickets
  function showTicketForm(reply) {
    ticketForm.hidden = false;
    ticketError.hidden = true;
    ticketForm.elements.subject.value = (reply && reply.suggested_subject && reply.kind !== "ticket_prompt") ? reply.suggested_subject : (ticketForm.elements.subject.value || "");
    if (!ticketForm.elements.description.value && reply.kind !== "ticket_prompt") ticketForm.elements.description.value = lastUserMessage;
    if (reply && reply.error_codes && reply.error_codes.length) ticketForm.elements.error_code.value = reply.error_codes[0];
    ticketForm.elements.subject.focus();
  }
  root.querySelector("[data-ticket-cancel]").addEventListener("click", () => {
    ticketForm.hidden = true;
    addBubble("assistant", "No problem — no ticket was created.");
    input.focus();
  });
  ticketForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = ticketForm.querySelector("[data-ticket-submit]");
    const payload = {
      confirm: true,
      subject: ticketForm.elements.subject.value.trim(),
      description: ticketForm.elements.description.value.trim(),
      error_code: ticketForm.elements.error_code.value,
      contact_email: ticketForm.elements.contact_email.value.trim(),
    };
    if (payload.subject.length < 4 || payload.description.length < 10) {
      ticketError.textContent = "Please add a subject (4+ characters) and a short description (10+ characters).";
      ticketError.hidden = false;
      return;
    }
    submit.disabled = true;
    submit.textContent = "Creating…";
    try {
      const { status, data } = await postJSON(root.dataset.ticketEndpoint, payload);
      if (status === 201 && data.ok && data.reference) {
        ticketForm.hidden = true;
        ticketForm.reset();
        const wrap = addBubble("assistant", data.message, "msg-success");
        const link = document.createElement("a");
        link.href = data.url;
        link.textContent = "View ticket " + data.reference;
        const sources = document.createElement("div");
        sources.className = "msg-sources";
        sources.appendChild(link);
        wrap.appendChild(sources);
      } else {
        const fieldErrors = data.fields ? Object.values(data.fields).flat().join(" ") : "";
        ticketError.textContent = fieldErrors || data.error || "The ticket could not be created. Please try again.";
        ticketError.hidden = false;
      }
    } catch (e) {
      ticketError.textContent = "The ticket could not be created because TripCraft couldn't be reached. Please try again.";
      ticketError.hidden = false;
    } finally {
      submit.disabled = false;
      submit.textContent = "Confirm & create ticket";
      scrollToEnd();
    }
  });
})();
