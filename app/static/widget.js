/* Website chat widget (P5.2). A company adds one tag to its site:
 *   <script src="https://OUR-SERVER/widget.js" data-company="SLUG" async></script>
 * Everything lives in a Shadow DOM, so the site's CSS can't change it and ours can't leak.
 * Text from the server is only ever set with textContent, never as HTML. */
(() => {
  "use strict";
  const me = document.currentScript;
  if (!me || window.__chatWidget) return; // added twice: one widget
  window.__chatWidget = true;

  const slug = me.getAttribute("data-company") || "";
  const api = new URL(me.src).origin + "/api/chat/" + encodeURIComponent(slug);
  const config = new URL(me.src).origin + "/api/widget-config/" + encodeURIComponent(slug);
  const NL = String.fromCharCode(10);
  const PAGE = 50; // the server's poll limit

  // Storage can throw (Safari private mode, blocked site data): then the id lives only in
  // `visitor` below, for this visit.
  const load = (key) => {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  };
  const save = (key, value) => {
    try {
      localStorage.setItem(key, value);
    } catch (e) {}
  };
  // getRandomValues, not randomUUID: phones on plain http (the demo) don't have randomUUID.
  const randomId = (bytes) =>
    Array.from(crypto.getRandomValues(new Uint8Array(bytes)), (b) =>
      b.toString(16).padStart(2, "0")
    ).join("");

  const KEY = "chat-widget:" + slug;
  let visitor = load(KEY);
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(visitor || "")) {
    visitor = randomId(16);
    save(KEY, visitor);
  }

  const ICON_CHAT =
    '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><path fill="currentColor" d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 4v-4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/></svg>';
  const ICON_CLOSE =
    '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" d="M6 6l12 12M18 6L6 18"/></svg>';
  const ICON_SEND =
    '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M3 20l18-8L3 4v6l12 2-12 2z"/></svg>';

  const CSS = `
* { box-sizing: border-box; font: inherit; }
.root { --c: #0f766e; font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto,
  "Noto Sans Bengali", "Hind Siliguri", sans-serif; color: #111827; }
button { cursor: pointer; border: 0; background: none; color: inherit; padding: 0; }
button:focus-visible, textarea:focus-visible, a:focus-visible {
  outline: 3px solid #2563eb; outline-offset: 2px; }
.launch { position: fixed; right: 20px; bottom: 20px; width: 60px; height: 60px;
  border-radius: 50%; background: var(--c); color: #fff; display: grid; place-items: center;
  box-shadow: 0 4px 16px rgba(0,0,0,.25); }
.panel { position: fixed; right: 20px; bottom: 92px; width: 370px; height: min(600px, calc(100vh - 112px));
  background: #fff; border-radius: 14px; box-shadow: 0 8px 32px rgba(0,0,0,.25);
  display: flex; flex-direction: column; overflow: hidden; }
.panel[hidden] { display: none; }
header { background: var(--c); color: #fff; padding: 12px 14px; display: flex;
  align-items: center; gap: 8px; font-weight: 600; }
header .title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
header button { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 8px; }
.log { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px;
  background: #f9fafb; }
.msg { max-width: 85%; padding: 8px 12px; border-radius: 12px; white-space: pre-wrap;
  overflow-wrap: anywhere; background: #fff; border: 1px solid #e5e7eb; align-self: flex-start; }
.msg.student { align-self: flex-end; background: var(--c); color: #fff; border-color: transparent; }
.note { font-size: 12px; color: #4b5563; align-self: center; text-align: center; }
.note a { color: inherit; }
.status { font-size: 13px; color: #92400e; background: #fef3c7; padding: 6px 12px; }
.status:empty { display: none; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 12px 0; }
.chips:empty { display: none; }
.chips button, .chips a { border: 1px solid var(--c); color: var(--c); border-radius: 999px;
  padding: 6px 12px; font-size: 14px; text-decoration: none; background: #fff; }
form { display: flex; gap: 8px; padding: 10px 12px; border-top: 1px solid #e5e7eb; }
textarea { flex: 1; resize: none; border: 1px solid #d1d5db; border-radius: 10px;
  padding: 8px 10px; max-height: 120px; font-size: 16px; color: #111827; background: #fff; }
form button { width: 44px; height: 44px; border-radius: 10px; background: var(--c); color: #fff;
  display: grid; place-items: center; }
@media (max-width: 480px) {
  .panel { inset: 0; width: 100%; height: 100%; border-radius: 0; }
  .launch { right: 16px; bottom: 16px; }
}`;

  const host = document.createElement("chat-widget");
  // Inline !important beats anything the site's stylesheets say about our element.
  host.style.cssText =
    "all: initial !important; display: block !important; position: fixed !important;" +
    " z-index: 2147483647 !important; width: 0 !important; height: 0 !important;" +
    " right: 0 !important; bottom: 0 !important;";
  const shadow = host.attachShadow({ mode: "open" });
  shadow.innerHTML = `<style>${CSS}</style><div class="root">
<button class="launch" type="button" aria-label="Open chat" aria-expanded="false">${ICON_CHAT}</button>
<div class="panel" role="dialog" hidden>
 <header><span class="title"></span>
  <button class="close" type="button" aria-label="Close chat">${ICON_CLOSE}</button></header>
 <div class="log" role="log" aria-live="polite"></div>
 <div class="status" role="status" aria-live="polite"></div>
 <div class="chips"></div>
 <form><textarea rows="1" maxlength="1000" aria-label="Message" placeholder="Type a message..."></textarea>
  <button type="submit" aria-label="Send">${ICON_SEND}</button></form>
</div></div>`;
  const $ = (selector) => shadow.querySelector(selector);
  const root = $(".root");
  const launch = $(".launch");
  const panel = $(".panel");
  const log = $(".log");
  const statusLine = $(".status");
  const chips = $(".chips");
  const input = $("textarea");

  let lastId = 0;
  let busy = 0; // messages being sent: poll results are dropped, so nothing shows twice
  let loaded = false;
  // Every retry that is waiting (a message and a poll can both be) ends when the network is back.
  const waiting = new Set();
  addEventListener("online", () => waiting.forEach((done) => done()));

  const add = (role, text) => {
    const div = document.createElement("div");
    div.className = "msg " + role;
    div.textContent = text;
    log.append(div);
    log.scrollTop = log.scrollHeight;
  };
  const note = (text, link, url) => {
    const p = document.createElement("p");
    p.className = "note";
    p.append(text);
    if (link) {
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = link;
      p.append(a, ".");
    }
    log.append(p);
  };
  const showButtons = (buttons, links) => {
    chips.replaceChildren();
    for (const { code, label } of buttons || []) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.addEventListener("click", () => send({ payload: code }, label));
      chips.append(b);
    }
    for (const [label, url] of links || []) {
      const a = document.createElement("a");
      a.href = url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = label;
      chips.append(a);
    }
  };

  const wait = (ms) =>
    new Promise((done) => {
      const finish = () => waiting.delete(finish) && done();
      waiting.add(finish);
      setTimeout(finish, ms);
    });

  // Waits as long as it takes: a dropped connection shows "Reconnecting..." and tries again.
  const request = async (url, options) => {
    let delay = 1000;
    for (;;) {
      let response = null;
      let body = null;
      try {
        response = await fetch(url, options);
        body = await response.text(); // the connection can also drop mid-body
      } catch (e) {
        response = null;
      }
      if (response && response.status === 429) {
        const seconds = Number(response.headers.get("Retry-After")) || 5;
        statusLine.textContent = "Too many messages. Sending again in a moment...";
        await wait(seconds * 1000);
      } else if (response && response.status < 500) {
        statusLine.textContent = "";
        return { ok: response.ok, body };
      } else {
        statusLine.textContent = "Reconnecting...";
        await wait(delay);
        delay = Math.min(delay * 2, 30000);
      }
    }
  };

  const reply = (body) => {
    for (const frame of body.split(NL + NL)) {
      const data = frame.split(NL).find((line) => line.startsWith("data: "));
      if (data) return JSON.parse(data.slice(6));
    }
    return null;
  };

  // One poll at a time: while offline, a poll every 4 s would otherwise pile up retry loops.
  let pulling = null;
  const pull = (everything) =>
    pulling || (pulling = pullPages(everything).finally(() => (pulling = null)));
  const pullPages = async (everything) => {
    for (;;) {
      const { ok, body } = await request(
        `${api}/poll?visitor=${visitor}&after=${lastId}`,
        { cache: "no-store" }
      );
      if (!ok || (busy && !everything)) return;
      const messages = JSON.parse(body).messages;
      for (const m of messages) {
        if (m.id <= lastId) continue;
        lastId = m.id;
        if (everything || m.role !== "student") add(m.role, m.text);
      }
      if (messages.length < PAGE) return;
    }
  };

  const send = async (body, shown) => {
    add("student", shown);
    chips.replaceChildren();
    busy++;
    try {
      const { ok, body: text } = await request(api, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Same id on every retry: the server answers a message once, however often it arrives.
        body: JSON.stringify({ visitor, id: randomId(12), ...body }),
      });
      if (!ok) {
        statusLine.textContent = "Sorry, that message couldn't be sent.";
        return;
      }
      const event = reply(text);
      // No text: already answered (a resend) or a person has taken over; the poll shows it.
      if (event && event.text && event.after > lastId) {
        lastId = event.after;
        add("bot", event.text);
        showButtons(event.buttons);
      }
    } finally {
      busy--;
    }
    if (!busy) pull(false); // a resent message is answered with nothing: the reply is stored
  };

  const open = async () => {
    panel.hidden = false;
    launch.setAttribute("aria-expanded", "true");
    input.focus();
    if (!loaded) {
      loaded = true;
      await pull(true);
    }
  };
  const close = () => {
    panel.hidden = true;
    launch.setAttribute("aria-expanded", "false");
    launch.focus();
  };

  launch.addEventListener("click", () => (panel.hidden ? open() : close()));
  $(".close").addEventListener("click", close);
  panel.addEventListener("keydown", (e) => e.key === "Escape" && close());
  input.addEventListener("keydown", (e) => {
    // isComposing: Enter that picks a word in a Bangla/phone keyboard must not send.
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $("form").requestSubmit();
    }
  });
  $("form").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    send({ text }, text);
  });

  // Phones: the on-screen keyboard shrinks the visible area; keep the input box above it.
  const fit = () => {
    const view = window.visualViewport;
    const small = window.matchMedia("(max-width: 480px)").matches;
    panel.style.height = small && view ? view.height + "px" : "";
    panel.style.top = small && view ? view.offsetTop + "px" : "";
  };
  if (window.visualViewport) visualViewport.addEventListener("resize", fit);
  addEventListener("resize", fit);

  // New messages from a counsellor, while the chat is open and the tab is visible.
  setInterval(() => {
    if (loaded && !panel.hidden && document.visibilityState === "visible") pull(false);
  }, 4000);

  (async () => {
    const { ok, body } = await request(config, { cache: "no-store" });
    if (!ok) return console.warn("chat widget: not available on this website");
    const c = JSON.parse(body);
    root.style.setProperty("--c", c.color); // checked by the server
    $(".title").textContent = c.name;
    panel.setAttribute("aria-label", "Chat with " + c.name);
    add("bot", c.greeting);
    log.lastChild.classList.add("greeting");
    note("By chatting you agree to our ", "privacy notice", c.privacy_url);
    const links = [];
    if (c.whatsapp) links.push(["Continue on WhatsApp", "https://wa.me/" + c.whatsapp]);
    if (c.messenger) links.push(["Continue on Messenger", "https://m.me/" + c.messenger]);
    showButtons(c.buttons, links);
    document.body.append(host);
    fit();
  })();
})();
