/* KENOGENESIS: Kosmokrator's browser structure, adapted to the CoE5 view model.
   DOM construction, shell, routing, forms and feedback follow the reference; project text is never HTML. */
(() => {
  "use strict";
  const $ = (s, root = document) => root.querySelector(s);
  const main = $("#main"), token = $('meta[name="kenogenesis-token"]').content;
  const state = {projects: [], models: new Map(), drafts: new Map(), receipts: new Map(), filters: new Map(), meta: null};
  const kinds = {monster: ["Units", "Unit", "units"], class: ["Classes", "Class", "classes"], weapon: ["Weapons", "Weapon", "weapons"],
    school: ["Ritual schools", "Ritual school", "schools"], ritual: ["Rituals", "Ritual", "rituals"], item: ["Items", "Item", "items"],
    terrain: ["Terrain", "Terrain", "terrain"], terraingroup: ["Terrain groups", "Terrain group", "terrain-groups"], event: ["Events", "Event", "events"],global:["Mod information","Mod information","mod-info"]};
  const tabKind = Object.fromEntries(Object.entries(kinds).map(([k, v]) => [v[2], k]));
  const groups = [["Browse", [["overview", "Overview"], ["classes", "Classes"], ["units", "Units"], ["weapons", "Weapons"],
    ["schools", "Ritual schools"], ["rituals", "Rituals"], ["items", "Items"], ["terrain", "Terrain"], ["events", "Events"]]],
    ["Build", [["design", "Design"], ["author", "Advanced tools"], ["validation", "Validation"], ["evidence", "Evidence"], ["export", "Export"]]]];
  const SCOPED_TABS = ["overview", "classes", "units", "design"];
  const secondary = [["source", "Source"], ["assets", "Assets"], ["other", "Other definitions"], ["docs", "Docs"]];
  const lastProjectHash = new Map();
  let seq = 0, fieldSeq = 0, rosterOpen = false, sidebarOpen = false, lastProject = "", previewTimer, previewAnchor, previewHideTimer, previewPlace, tabsObserver;

  // The reference's safe DOM builder: project strings are always text nodes.
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (key === "value") node.value = value;
      else node.setAttribute(key, value === true ? "" : String(value));
    }
    for (const child of children.flat(Infinity)) if (child !== null && child !== undefined && child !== false)
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return node;
  }
  const p = (text, cls) => el("p", {text, class: cls});
  const badge = (text, cls = "info") => el("span", {class: `badge ${cls}`, text});
  const btn = (text, fn, cls = "") => el("button", {type: "button", class: `btn ${cls}`, onclick: fn}, text);
  const link = (text, href, cls = "") => el("a", {href, class: cls, text});
  const stack = (...xs) => el("div", {class: "stack"}, xs);
  const panel = (title, ...xs) => el("section", {class: "panel"}, el("h3", {text: title}), xs);
  const details = (title, ...xs) => el("details", {class: "tech"}, el("summary", {text: title}), xs);
  // label[for] names the control; help is a description, so signatures and line numbers stay out of the accessible name.
  // extra: an optional live status node (such as a reference check) that also describes the control.
  const field = (label, input, help, extra) => {
    if (!input.id) input.id = `field-${++fieldSeq}`;
    if (extra) extra.id = `${input.id}-status`;
    const described = [help ? `${input.id}-hint` : null, extra ? extra.id : null].filter(Boolean).join(" ");
    if (described) input.setAttribute("aria-describedby", described);
    return el("div", {class: "edit-field"}, el("label", {for: input.id, text: label}), input,
      help ? el("div", {class: "field-meta faint", id: `${input.id}-hint`, text: help}) : null, extra || null);
  };
  const input = (name, value = "", type = "text") => el("input", {class: "input", name, value, type});
  const area = (name, value = "", rows = 5) => el("textarea", {class: "input", name, rows, spellcheck: "false", text: value});
  const select = (name, options, value = "") => {
    const s = el("select", {class: "input", name}, options.map(([v, label]) => el("option", {value: v, text: label})));
    s.value = String(value); return s;
  };
  const short = (s) => s ? `${s.slice(0, 12)}…` : "—";
  const path = (...parts) => `#/${parts.map(encodeURIComponent).join("/")}`;
  const parts = () => location.hash.slice(2).split("?")[0].split("/").filter(Boolean).map(decodeURIComponent);
  const query = () => new URLSearchParams(location.hash.split("?")[1] || "");
  const scope = () => query().get("c") || "all";
  // CoE5 definitions have no stable ID here: links name a block by its position in the source. Every link to a position
  // (a definition, its edit or duplicate form, an Advanced block) records the saved revision it was made for as ?rev=
  // (the first 16 hex digits); linkGuard() checks it before anything positional opens.
  const pinOf = (m) => m.revision.slice(0, 16);
  const positional = (tab, tail) => {const [a = "", b = ""] = tail.map(String);
    return tab === "source" ? /^\d+$/.test(a) : tab === "author" ? a === "block" : !!tabKind[tab] && tabKind[tab] !== "global" && (/^\d+$/.test(a) || (["edit", "new"].includes(a) && /^\d+$/.test(b)));};
  const route = (m, tab = "overview", ...tail) => {const q = new URLSearchParams();
    if (SCOPED_TABS.includes(tab)) q.set("c", state.linkGuard?.status === "stale" ? "all" : scope());
    if (positional(tab, tail) || /^\d+$/.test(q.get("c") || "")) q.set("rev", pinOf(m));
    return path("p", m.project.slug, tab, ...tail) + (String(q) ? `?${q}` : "");};
  const sourceLink = (m, line, label = `line ${line}`) => link(label, route(m, "source", line));
  const kindRoute = (m, o) => route(m, kinds[o.kind]?.[2] || "other", o.index);
  function table(head, rows) {
    return el("div", {class: "table-wrap"}, el("table", {class: "data"},
      el("thead", null, el("tr", null, head.map(x => el("th", {scope: "col"}, x)))),
      el("tbody", null, rows.map(row => el("tr", null, row.map(x => el("td", null, x)))))));
  }
  function stateBox(type, title, text) {
    return el("div", {class: `state state-${type}`, role: type === "error" ? "alert" : "status"},
      type === "loading" ? el("span", {class: "spinner", "aria-hidden": "true"}) : null,
      el("strong", {text: title}), text ? p(text) : null);
  }
  // One error presentation for every failure. Transport failures (see failure()) explain recovery and draft retention;
  // a typed server error keeps its [code] message and structured details. what names the resource that failed to load.
  // Nothing here retries a write: Retry is only offered by callers, and only for reads.
  function errorBox(e, retry, what, retryId) {
    const code = e?.code, message = e?.message || String(e), cause = [];
    let title = code ? `[${code}] ${message}` : message;
    if (code === "network_error" || code === "bad_response") {
      title = `${what ? `Could not load ${what}. ` : ""}${message}`;
      cause.push(code === "network_error" ?
        `Check that the KENOGENESIS server for this page (${location.host}) is still running, or start it again the way you launched it, then ${retry ? "use Retry" : "try again"}.` :
        `The server may have restarted, or another program may be answering on ${location.host}. ${retry ? "Use Retry" : "Try again"}; if it keeps happening, restart KENOGENESIS.`);
      cause.push(e.write ? "Your entries are kept and nothing was resent automatically. If the server stopped during a save, reload the latest file before reviewing again." :
        "Unsaved drafts stay in this browser tab while it remains open; reloading the page can lose them.");
    } else if (what) {cause.push(title); title = `Could not load ${what}.`;}
    const rt = code === "network_error" && state.meta?.runtime?.python_executable ? cliSetup() : null;
    const info = e?.details && typeof e.details === "object" && Object.keys(e.details).length ? e.details : null;
    const again = retry ? btn("Retry", retry) : null; if (again && retryId) again.id = retryId;
    return stack(stateBox("error", title, cause.join(" ")),
      rt ? details("Start command for this workspace", el("pre", {class: "code", tabindex: "0", text: rt.run(`serve --port ${location.port || 80}`)}),
        el("ul", {class: "art-notes"}, rt.notes.map(n => el("li", {text: n})))) : null,
      info ? details("Error details", el("pre", {class: "code", text: JSON.stringify(info, null, 2)})) : null, again);
  }
  function toast(text) {
    let box = $("#toast"); if (!box) document.body.append(box = el("div", {id: "toast", class: "toast", role: "status"}));
    box.textContent = text; box.hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => {box.hidden = true;}, 2200);
  }
  // Browser storage can be unavailable (private mode, blocked site data); preferences are then simply not remembered.
  const storeGet = (area, key) => {try {return window[area].getItem(key);} catch (_) {return null;}};
  const storeSet = (area, key, value) => {try {value === null ? window[area].removeItem(key) : window[area].setItem(key, value);} catch (_) { /* not remembered */ }};
  // A persistent inline error for one control: linked by aria-describedby, marked aria-invalid, cleared when edited.
  function markInvalid(control, message) {
    if (!control.id) control.id = `field-${++fieldSeq}`;
    const id = `${control.id}-error`, host = control.closest(".edit-field") || control.parentElement;
    let box = host.querySelector(":scope > .field-err");
    if (!box) host.append(box = el("div", {class: "field-err", id}));
    box.textContent = message; control.setAttribute("aria-invalid", "true");
    const ids = (control.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
    if (!ids.includes(id)) control.setAttribute("aria-describedby", [...ids, id].join(" "));
    const clear = () => {control.removeAttribute("aria-invalid"); box.textContent = "";};
    control.addEventListener("input", clear, {once: true}); control.addEventListener("change", clear, {once: true});
  }
  // Open any collapsed disclosure around a control before focusing it, so the first invalid input is reachable.
  function reveal(control) {
    for (let x = control.parentElement; x; x = x.parentElement) if (x.tagName === "DETAILS") x.open = true;
    control.focus(); control.scrollIntoView?.({block: "center"});
  }
  const invalid = (control, message) => {markInvalid(control, message); reveal(control);};
  // Typed request failures: network_error (the local server did not answer), bad_response (the reply was not the
  // expected JSON), the server's own {code, message, details}, or http_<status> when a non-OK reply carries no typed error.
  // Only the status line and the server's typed fields are kept; raw response text is never shown. An aborted request
  // rethrows the browser's AbortError unchanged so superseded callers can ignore it.
  const failure = (code, message, extra) => Object.assign(new Error(message), {code}, extra || {});
  async function send(url, init, write = false) {
    try {return await fetch(url, init);}
    catch (e) {if (init?.signal?.aborted || e?.name === "AbortError") throw e;
      throw failure("network_error", "The local KENOGENESIS server did not respond.", {write});}
  }
  async function typedError(r, write = false) {
    let body = null; try {body = await r.json();} catch (e) {if(e?.name === "AbortError") throw e; /* not JSON: fall back to the HTTP status */ }
    const x = body?.error;
    if (x && typeof x.code === "string" && typeof x.message === "string") return failure(x.code, x.message, {details: x.details, status: r.status, write});
    return failure(`http_${r.status}`, r.statusText || `HTTP ${r.status}`, {status: r.status, write});
  }
  async function readJson(r, write) {
    let body; try {body = await r.json();} catch (e) {if(e?.name === "AbortError") throw e; throw failure("bad_response", `The local server's reply could not be read (HTTP ${r.status}).`, {status: r.status, write});}
    if (!body || typeof body !== "object" || Array.isArray(body) || typeof body.ok !== "boolean" ||
        (body.ok && !Object.prototype.hasOwnProperty.call(body,"result")))
      throw failure("bad_response", `The local server sent an unexpected reply (HTTP ${r.status}).`, {status: r.status, write});
    const x = body.error;
    if (!r.ok || body.ok === false || (write && !body.ok)) throw x && typeof x.code === "string" ? failure(x.code, String(x.message || r.statusText), {details: x.details, status: r.status, write}) :
      failure(`http_${r.status}`, r.statusText || `HTTP ${r.status}`, {status: r.status, write});
    return body.result;
  }
  async function get(url, signal) {return readJson(await send(url, {signal}));}
  async function post(op, args) {
    return readJson(await send(`/api/${op}`, {method: "POST", headers: {"Content-Type": "application/json", "X-Kenogenesis-Token": token}, body: JSON.stringify(args)}, true), true);
  }
  // Plain-text and file reads (source, guides, map headers) with the same typed failures as get().
  async function getOk(url, signal) {const r = await send(url, {signal}); if (!r.ok) throw await typedError(r); return r;}
  async function getText(url, signal) {
    const r = await getOk(url, signal);
    try {return await r.text();} catch (e) {if (signal?.aborted || e?.name === "AbortError") throw e; throw failure("network_error", "The connection to the local KENOGENESIS server was interrupted.");}
  }
  const base = (m) => `/api/projects/${encodeURIComponent(m.project.slug)}`;
  // Read-only shared operations use the same GET route as the CLI/MCP operation names.
  const api = (op, args) => get(`/api/${op}?args=${encodeURIComponent(JSON.stringify(args))}`);
  async function model(slug, fresh = false) {
    if (fresh || !state.models.has(slug)) {const m = await get(`/api/projects/${encodeURIComponent(slug)}`); state.models.set(slug, m);}
    return state.models.get(slug);
  }
  function activeDrafts(slug) {return [...state.drafts.values()].filter(d => d.dirty && (!slug || d.slug === slug));}
  // Keep old positional drafts intact for explicit recovery; do not move or rebind them on a model refresh.
  function carryDrafts(m) {
    for (const d of state.drafts.values()) if (d.slug === m.project.slug && d.keyRev && d.keyRev !== pinOf(m) && /:\d+$/.test(d.key)) d.unplaced = true;
  }
  function draft(key, initial) {
    if (!state.drafts.has(key)) state.drafts.set(key, {...initial, key, dirty: false});
    return state.drafts.get(key);
  }
  function dirty(d) {d.dirty = true; syncDrafts();}
  function syncDrafts() {
    const target = $("#draft-status"); if (!target) return;
    const ds = activeDrafts(target.dataset.slug); target.hidden = !ds.length;
    target.textContent = `${ds.length} unsaved draft${ds.length === 1 ? "" : "s"}`;
  }
  window.addEventListener("beforeunload", e => {if (activeDrafts().length) {e.preventDefault(); e.returnValue = "";}});
  function recordReceipt(m, result, title) {
    const slug = m.project.slug, list = state.receipts.get(slug) || [];
    list.unshift({title, time: new Date().toLocaleTimeString(), ...result}); state.receipts.set(slug, list.slice(0, 5));
  }
  function receiptPanel(m) {
    const list = state.receipts.get(m.project.slug) || []; if (!list.length) return null;
    const facts=r=>el("dl",{class:"kv receipt-facts"},el("dt",{text:"File"}),el("dd",{text:r.file||m.provenance.file}),el("dt",{text:"Revision"}),
      el("dd",{class:"mono",text:`${short(r.before_revision)} → ${short(r.revision)}`}),r.backup?[el("dt",{text:"Backup"}),el("dd",{class:"mono",text:r.backup})]:null,
      r.assets?.length?[el("dt",{text:"Artwork"}),el("dd",{text:r.assets.map(a=>a.path).join(", ")})]:null);
    const dismiss=btn("Dismiss",()=>{state.receipts.delete(m.project.slug);render();},"btn-ghost btn-small receipt-dismiss");dismiss.setAttribute("aria-label","Dismiss save receipts for this project");
    return el("section", {class: "receipt", "aria-labelledby": "receipt-h"},el("div",{class:"receipt-head"},el("h2",{id:"receipt-h",class:"receipt-title"},badge("saved","ok")," ",list[0].title),
      el("span",{class:"faint",text:list[0].time}),dismiss),facts(list[0]),
      list.length>1?details(`Earlier saves (${list.length-1})`,el("ol",{class:"receipt-older"},list.slice(1).map(r=>el("li",null,p(`${r.title} · ${r.time}`),facts(r))))):null);
  }
  // Project cards and catalog navigation keep the same DOM classes as Kosmokrator.
  function renderSidebar(slug) {
    let filter = $("#project-filter");
    if (!filter && state.projects.length > 5) {
      filter = input("project-filter", "", "search"); filter.id = "project-filter"; filter.classList.add("project-filter");
      filter.placeholder = "Find a project"; filter.setAttribute("aria-label", "Filter projects");
      $("#project-list").before(filter); filter.addEventListener("input", () => renderSidebar(parts()[0] === "p" ? parts()[1] : null)); syncSidebar();
    }
    const q = filter?.value.toLowerCase() || "";
    // The current project stays listed whatever the filter says.
    const shown = state.projects.filter(x => x.slug === slug || `${x.name} ${x.slug}`.toLowerCase().includes(q));
    // An unreadable project has no page to open: it is a card with its error, not a link.
    $("#project-list").replaceChildren(...shown.map(x => !x.ok ?
      el("div", {class: "project-card is-broken", role: "group", "aria-label": `${x.slug} (unreadable)`},
        el("div", {class: "pc-text"}, el("div", {class: "title", text: x.slug}),
          el("div", {class: "meta"}, badge("Unreadable", "err"), el("span", {class: "mono", text: x.error?.code || "unreadable"})),
          x.error?.message ? el("div", {class: "faint", text: x.error.message}) : null)) :
      el("a", {class: "project-card", href: path("p", x.slug), "aria-current": x.slug === slug ? "page" : null, title: `${x.name || x.slug} (${x.slug})`},
        x.banner?.url ? el("img", {class: "mod-banner", src: x.banner.url, alt: "", loading: "lazy"}) : el("span", {class: "mod-banner placeholder", text: "—"}),
        el("div", {class: "pc-text"}, el("div", {class: "title", text: x.name || x.slug}),
          el("div", {class: "meta"}, x.target_version ? `CoE5 ${x.target_version}` : "",
            x.validation?.counts.error ? badge(`${x.validation.counts.error} errors`, "err") : null)))));
    if (!state.projects.length) $("#project-list").append(p("No projects yet.", "faint sidebar-empty"));
    else if (!shown.length) $("#project-list").append(el("p", {class: "faint sidebar-empty", role: "status", text: "No project matches."}));
    renderCatalogNav(slug);
  }
  // The catalog reads one project's catalog; without a current project it names the last selected or first readable one.
  function renderCatalogNav(slug) {
    const readable = state.projects.filter(x => x.ok), find = s => s && readable.find(x => x.slug === s);
    let target = find(slug), why = null;
    if (target) {lastProject = target.slug; storeSet("localStorage", "kenogenesis:lastProject", target.slug);}
    else if ((target = find(lastProject) || find(storeGet("localStorage", "kenogenesis:lastProject")))) why = "Last selected project";
    else if ((target = readable[0])) why = "First project";
    if (!target) {$("#catalog-nav").replaceChildren(p("Create or import a project first.", "faint sidebar-empty")); return;}
    const name = target.name || target.slug, xs = parts(), here = !why && xs[0] === "p" && xs[1] === target.slug && xs[2] === "inspector";
    $("#catalog-nav").replaceChildren(el("a", {class: "catalog-link", href: path("p", target.slug, "inspector"), "aria-current": here ? "page" : null,
      "aria-label": `Vanilla catalog for ${name} (${target.slug})${why ? `, ${why.toLowerCase()}` : ""}`},
      el("span", {class: "title", text: "Vanilla catalog"}), why ? el("span", {class: "faint", text: `${why}: ${name}`}) : null));
  }
  async function reloadProjects() {state.projects = (await get("/api/projects")).projects; renderSidebar(parts()[1]);}
  $("#reload-btn").addEventListener("click", async () => {
    try {state.models.clear(); await reloadProjects(); await render(); toast("Projects reloaded; drafts kept.");} catch(e) {toast(e.message);}
  });
  function moreMenu(m, active) {
    const cur = secondary.find(x => x[0] === active), counts = {assets: m.counts.assets, other: m.objects.filter(o => o.kind === "terraingroup").length};
    const list = el("ul", {class: "tab-more-list", id: "tab-more-list", hidden: true},
      secondary.map(([k, t]) => el("li", null, el("a", {href: route(m, k), "aria-current": k === active ? "page" : null}, t,
        counts[k] === undefined ? null : el("span", {class: "count", text: counts[k]})))));
    const b = btn([cur ? `More: ${cur[1]}` : "More", el("span", {class: "caret", "aria-hidden": "true", text: "▾"})], () => setOpen(list.hidden), `tab-more-btn${cur ? " is-current" : ""}`);
    b.setAttribute("aria-expanded", "false"); b.setAttribute("aria-controls", "tab-more-list");
    const wrap = el("div", {class: "tab-more"}, b, list);
    function setOpen(open, focus = false) {list.hidden = !open; b.setAttribute("aria-expanded", String(open));
      if (focus) (open ? $('a[aria-current="page"]', list) || $("a", list) : b).focus();}
    wrap.addEventListener("keydown", e => {
      if (e.key === "Escape") {e.preventDefault(); setOpen(false, true);}
      if (["ArrowDown", "ArrowUp"].includes(e.key)) {e.preventDefault(); if (list.hidden) return setOpen(true, true);
        const links = [...list.querySelectorAll("a")], i = links.indexOf(document.activeElement);
        (links[Math.max(0, Math.min(links.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))] || b).focus();}
    });
    wrap.addEventListener("focusout", e => {if (!wrap.contains(e.relatedTarget)) setOpen(false);});
    return wrap;
  }
  function projectShell(m, active) {
    const title = el("h1", {id: "page-title", tabindex: "-1", text: m.project.name});
    const head = el("div", {class: "proj-head"}, m.project.banner?.url ? el("img", {class: "mod-banner", src: m.project.banner.url, alt: `${m.project.name} banner`}) : null,
      el("div", {class: "proj-title"}, title, el("div", {class: "sub", text: `Conquest of Elysium 5${m.project.target_version ? ` · ${m.project.target_version}` : ""}`})),
      el("div", {class: "proj-actions"}, el("a", {id: "draft-status", class: "badge warn draft-status", href: path("p", m.project.slug, "export"), "data-slug": m.project.slug, hidden: true})));
    const classList = m.objects.filter(o => o.kind === "class");
    const picker = classList.length && SCOPED_TABS.includes(active) ? select("class-select",
      [["all", "All classes"], ...classList.map(o => [String(o.index), o.display]), ["none", "Not tied to a class"]], state.linkGuard?.status === "stale" ? "all" : scope()) : null;
    if (picker) {picker.id = "class-select"; picker.addEventListener("change", () => {const url = new URLSearchParams(query()); url.set("c", picker.value);
      storeSet("localStorage", `kenogenesis:class:${m.project.slug}`, JSON.stringify({value:picker.value,rev:pinOf(m)}));
      const reset=state.linkGuard?.status === "stale";
      if(reset){for(const key of ["refs","ref","cmp","crefs"])url.delete(key);}
      if(reset || /^\d+$/.test(picker.value))url.set("rev",pinOf(m));
      location.hash = (active==="classes" || reset ? path("p",m.project.slug,active) : path(...parts())) + `?${url}`;});}
    const tabs = el("div", {class: "tabs-scroll", id: "tabs-scroll"}, groups.map(([label, entries]) =>
      el("div", {class: `tab-group tab-group-${label === "Browse" ? "browse" : "edit"}`, role: "group", "aria-label": label}, entries.map(([key, label]) => {
        const count = key==="units"?scoped(m,m.objects.filter(o=>o.kind==="monster")).length:tabKind[key] ? m.counts[tabKind[key]] : key === "validation" ? Object.values(m.validation.counts).reduce((a,b) => a+b,0) : null;
        const flag = key === "export" ? exportFlag(m) : null;
        return el("a", {href: route(m, key), "aria-current": key === active ? "page" : null, title: flag?.title || null}, label,
          count === null ? null : el("span", {class: "count", text: count}), flag ? el("span", {class: `tab-flag ${flag.kind}`, text: flag.text}) : null);
      }))));
    const motion=()=>matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth";
    const prev = btn("‹", () => tabs.scrollBy({left: -Math.max(120, tabs.clientWidth * .7), behavior: motion()}), "tabs-nudge tabs-prev");
    const next = btn("›", () => tabs.scrollBy({left: Math.max(120, tabs.clientWidth * .7), behavior: motion()}), "tabs-nudge tabs-next");
    prev.setAttribute("aria-label", "Scroll section tabs left"); next.setAttribute("aria-label", "Scroll section tabs right");
    for (const b of [prev, next]) {b.hidden = true; b.setAttribute("aria-controls", "tabs-scroll");}
    const nav = el("nav", {class: "tabs", "aria-label": "Project sections"}, el("div", {class: "tabs-rail"}, prev, tabs, next), moreMenu(m, active));
    // A focused scroll button that disappears hands focus to the nearest tab instead of dropping it to the page.
    const update = () => {const max = tabs.scrollWidth - tabs.clientWidth;
      for (const [b, on] of [[prev, max > 1 && tabs.scrollLeft > 1], [next, max > 1 && tabs.scrollLeft < max - 1]]) {
        if (!on && !b.hidden && document.activeElement === b) {const ls = [...tabs.querySelectorAll("a")]; (b === prev ? ls[0] : ls.at(-1))?.focus({preventScroll: true});}
        b.hidden = !on;}};
    tabs.addEventListener("scroll", update, {passive: true}); tabsObserver=new ResizeObserver(update);tabsObserver.observe(tabs); requestAnimationFrame(() => {
      update(); const a = $('[aria-current="page"]', tabs);
      // Only the strip scrolls, never the page.
      if (a && tabs.scrollWidth > tabs.clientWidth + 1) {const sr = tabs.getBoundingClientRect(), ar = a.getBoundingClientRect(); tabs.scrollLeft += ar.left + ar.width / 2 - (sr.left + sr.width / 2);}
    });
    nav.addEventListener("keydown", e => {if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return; const links = [...nav.querySelectorAll(".tabs-scroll a,button.tab-more-btn")];
      const i = links.indexOf(document.activeElement); if (i >= 0) {e.preventDefault(); links[(i + (e.key === "ArrowRight" ? 1 : links.length-1)) % links.length].focus();}});
    if(picker)$(".proj-actions",head).prepend(el("div", {class: "nation-bar"}, el("label", {for: "class-select", text: "Class"}), picker));
    return [head, receiptPanel(m), nav];
  }
  // Export tab flag: static errors block export; an older (or unreadable) latest export only needs a fresh export, which is allowed.
  function exportFlag(m) {
    const L = m.latest_export;
    if (!m.validation.static_ok) return {kind: "err", text: "blocked", title: "Static errors block export until fixed"};
    if (L?.error) return {kind: "warn", text: "check", title: "The latest export manifest could not be read; you can export again"};
    if (L && L.revision !== m.revision) return {kind: "warn", text: "outdated", title: "The latest export is of an older revision; you can export the saved revision now"};
    return null;
  }
  function catalogStatus(m) {
    const box = $("#catalog-status"); box.replaceChildren();
    if (!m) return;
    if (!m.catalog.available) box.append(link("No local catalog", route(m, "overview", "settings")));
    else if (m.catalog.game_version !== m.project.target_version) box.append(badge("Catalog version differs", "warn"));
    if (m.catalog.source === "snapshot") box.append(badge("Catalog: private snapshot", "warn"));
    else if (["stale", "invalid"].includes(m.catalog.snapshot?.status)) box.append(badge(`Snapshot ${m.catalog.snapshot.status}`, "warn"));
    if (m.project.target_version && m.project.target_version !== m.manual.version) box.append(badge(`Manual ${m.manual.version}`, "info"));
    if (m.game_profile?.release_notes?.length) box.append(badge(`${m.game_profile.release_notes[0].version} release notes`, "info"));
  }
  function diagnostics(m, items = m.validation.diagnostics) {
    if (!items.length) return stateBox("ok", "No diagnostics.");
    return stack(...["error", "warning", "unverified"].map(severity => {
      const rows = items.filter(x => x.severity === severity); if (!rows.length) return null;
      return panel(`${severity === "error" ? "Errors" : severity === "warning" ? "Warnings" : "Unverified"} (${rows.length})`,
        table(["Location", "Issue"], rows.map(x => [x.line ? sourceLink(m, x.line) : x.file || "Project", stack(p(x.message), p(x.code, "faint mono"))])));
    }));
  }
  function settings(m) {
    const d = draft(`${m.project.slug}:settings`, {slug: m.project.slug, label: "Project settings", href: route(m, "overview", "settings"),
      values: {target_version: m.project.target_version || "", catalog: m.project.catalog || "", dependencies: m.project.dependencies.join("\n"), declared_assets: m.project.declared_assets.join("\n")}});
    const form = el("form", {class: "stack"}), result = el("div");
    // Any edit makes an open review or an earlier error stale; the draft values themselves are always kept.
    const edited = () => {dirty(d); if (!d.busy) result.replaceChildren();};
    for (const [key, label] of [["target_version", "Target game version"], ["catalog", "Local catalog path"], ["dependencies", "Dependency projects"], ["declared_assets", "Additional export files (one per line)"]]) {
      if (key === "dependencies") {form.append(dependencyEditor(m, d, edited)); continue;}
      const control = key === "declared_assets" ? area(key, d.values[key], 3) : input(key, d.values[key]);
      control.addEventListener("input", () => {d.values[key] = control.value; edited();});
      form.append(field(label, control));
    }
    form.append(el("button", {class: "btn", type: "submit", text: "Review settings"}), result);
    form.addEventListener("submit", e => {e.preventDefault(); const args = {project: m.project.slug, expected_revision: m.revision,
      target_version: d.values.target_version || null, catalog: d.values.catalog || null,
      dependencies: d.values.dependencies.split(/\r?\n/).map(x=>x.trim()).filter(Boolean), declared_assets: d.values.declared_assets.split(/\r?\n/).map(x=>x.trim()).filter(Boolean)};
      reviewWrite(m, d, form, result, "configure_project", {...args, preview: true}, "configure_project", {...args, preview: false});});
    return panel("Project settings", form);
  }
  // Direct dependency projects in declared order, edited as rows of the settings draft; nothing is saved until the guarded
  // settings review. Entries that do not resolve stay editable and are reported, never dropped. Declared order is what
  // KENOGENESIS records and checks: the engine's activation order is not verified, so no project is said to win an overlap.
  function dependencyEditor(m,d,edited){
    const self=m.project.slug;
    const list=el("ol",{class:"dep-list","aria-label":"Declared dependency order"}),orderLine=el("p",{class:"faint dep-order"}),feedback=el("p",{class:"field-meta",role:"status","aria-live":"polite"});
    const deps=()=>d.values.dependencies.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    const known=slug=>state.projects.find(x=>x.slug===slug);
    const status=(slug,i,xs)=>{const x=known(slug);
      if(slug===self)return ["this project","err","A project cannot depend on itself; remove this entry."];
      if(xs.indexOf(slug)!==i)return ["duplicate","err","Listed more than once; remove this entry."];
      if(!SLUG_RE.test(slug))return ["not a slug","err","Not a valid project folder name; remove it and add the correct name."];
      if(!x)return ["not found","warn","No project folder with this name in the workspace. Kept as written; the review will refuse it until it exists."];
      if(!x.ok)return ["unreadable","warn",x.error?.message||"The project cannot be read."];
      return ["project","ok",x.name&&x.name!==slug?x.name:null];};
    let addPick=null;
    const picker=select("dep-pick",[]),manual=input("dep-manual");manual.placeholder="project_folder_name";manual.setAttribute("autocomplete","off");manual.spellcheck=false;
    function fillPicker(){const xs=deps(),opts=state.projects.filter(x=>x.ok&&x.slug!==self&&!xs.includes(x.slug));
      picker.replaceChildren(el("option",{value:"",text:opts.length?"Choose a project":"No other readable project to add"}),
        ...opts.map(x=>el("option",{value:x.slug,text:x.name&&x.name!==x.slug?`${x.name} (${x.slug})`:x.slug})));picker.disabled=!opts.length;if(addPick)addPick.disabled=!opts.length;}
    function set(xs,message,focus){d.values.dependencies=xs.join("\n");for(const c of [manual,picker]){c.removeAttribute("aria-invalid");c.closest(".edit-field")?.querySelector(".field-err")?.replaceChildren();}edited();show();feedback.textContent=message;
      if(focus)(list.querySelector(focus)||manual).focus();}
    function add(slug,control){const xs=deps();slug=slug.trim();
      if(!slug){invalid(control,control===picker?"Choose a project to add.":"Enter a project folder name.");return;}
      if(!SLUG_RE.test(slug)){invalid(control,"Use a project folder name: 2–48 lowercase letters, digits or underscores, starting with a letter.");return;}
      if(slug===self){invalid(control,"A project cannot depend on itself.");return;}
      if(xs.includes(slug)){invalid(control,`${slug} is already listed.`);return;}
      if(xs.length>=32){invalid(control,"Declare at most 32 direct dependencies.");return;}
      manual.value="";set([...xs,slug],`Added ${slug} at the end of the declared order${known(slug)?.ok?"":"; it is not a readable project in this workspace yet"}. Review settings to save.`);control.focus();}
    function show(){const xs=deps();
      list.replaceChildren(...xs.map((dep,i)=>{const [label,kind,note]=status(dep,i,xs);
        const move=(j,dir)=>{const ys=[...xs];[ys[i],ys[j]]=[ys[j],ys[i]];set(ys,`Moved ${dep} to position ${j+1}. Review settings to save.`,`li:nth-child(${j+1}) button[data-dir="${dir}"]:not([disabled])`);};
        return el("li",{class:"dep-item"},el("span",{class:"dep-name"},el("span",{class:"mono",text:dep})," ",badge(label,kind),note?el("span",{class:"faint dep-note",text:` ${note}`}):null),
          el("span",{class:"btn-row dep-actions"},
            el("button",{type:"button",class:"btn btn-small btn-ghost","data-dir":"up",disabled:i===0,"aria-label":`Move ${dep} earlier`,onclick:()=>move(i-1,"up")},"↑"),
            el("button",{type:"button",class:"btn btn-small btn-ghost","data-dir":"down",disabled:i===xs.length-1,"aria-label":`Move ${dep} later`,onclick:()=>move(i+1,"down")},"↓"),
            el("button",{type:"button",class:"btn btn-small btn-ghost","aria-label":`Remove ${dep}`,onclick:()=>set(xs.filter((_,k)=>k!==i),`Removed ${dep}. Review settings to save.`,
              `li:nth-child(${Math.min(i+1,xs.length-1)}) button[aria-label^="Remove"]`)},"Remove")));}));
      if(!xs.length)list.append(el("li",{class:"faint dep-empty",text:"No dependencies declared."}));
      orderLine.textContent=`Declared order: ${[...xs,`${self} (this project, last)`].join(" → ")}. KENOGENESIS checks dependencies first, then this project. This is the declared order only; the engine's activation order and equal-priority behaviour are not verified.`;
      fillPicker();}
    addPick=btn("Add project",()=>add(picker.value,picker),"btn-small");const addManual=btn("Add by name",()=>add(manual.value,manual),"btn-small btn-ghost");
    manual.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();add(manual.value,manual);}});
    show();
    return el("fieldset",{class:"edit-group dep-editor"},el("legend",{text:"Dependency projects"}),
      p("Other projects in this workspace that this mod needs installed. Up to 32, flat (a dependency cannot declare its own). They are not bundled in the export.","faint"),
      list,orderLine,el("div",{class:"btn-row"},field("Add a readable project",picker),addPick),
      el("div",{class:"btn-row"},field("Or enter a project folder name",manual,"For a project that is not readable yet; the review checks it."),addManual),feedback);
  }
  // Reference files are read in the browser and sent as content; the server saves a new private catalog file only.
  function catalogImport(m) {
    const d = draft(`${m.project.slug}:catalog-import`, {slug: m.project.slug, label: "Reference catalog import", href: route(m, "overview", "catalog-import"),
      values: {name: "", game_version: "", provenance: ""}, files: []});
    const form = el("form", {class: "stack"}), result = el("div");
    for (const [key, label, help] of [["name", "Catalog name", "Saved as catalogs/<name>.json in the workspace; existing catalogs are never overwritten."],
      ["game_version", "Game version of the files", "The version the files describe, such as 5.22. A mismatch with the target version is reported."],
      ["provenance", "Provenance", "Source, exact revision and license of the files. Stored with each file's SHA-256."]]) {
      const control = key === "provenance" ? area(key, d.values[key], 3) : input(key, d.values[key]);
      if (key !== "provenance") control.required = true;
      control.addEventListener("input", () => {d.values[key] = control.value; dirty(d);}); form.append(field(label, control, help));
    }
    const chosen = el("div", {class: "field-meta faint", "aria-live": "polite", text: d.files.length ? `Selected: ${d.files.map(f => f.filename).join(", ")}` : "No files selected."});
    const files = input("reference-files", "", "file"); files.multiple = true; files.accept = ".c5m";
    // The earlier selection is dropped before reading, so a pending or failed read never submits the previous files.
    files.addEventListener("change", async () => {
      const list = [...files.files], mine = d.readTicket = (d.readTicket || 0) + 1;
      d.reading = true; d.files = []; result.replaceChildren();
      try {
        if (list.length > 12 || list.reduce((n, f) => n + f.size, 0) > 8 * 1024 * 1024) throw new Error("Choose at most 12 files, totalling at most 8 MiB.");
        chosen.textContent = "Reading files…"; const read = await Promise.all(list.map(upload)); if (mine !== d.readTicket) return; d.files = read; dirty(d);
        chosen.textContent = d.files.length ? `Selected: ${d.files.map(f => f.filename).join(", ")}` : "No files selected.";
      } catch (e) {if (mine !== d.readTicket) return; d.files = []; files.value = ""; chosen.textContent = "No files selected."; result.replaceChildren(errorBox(e));}
      finally {if (mine === d.readTicket) d.reading = false;}
    });
    form.append(field("Reference .c5m files", files, "Local reference data you are allowed to use. Nothing is uploaded beyond this local server."), chosen,
      el("button", {class: "btn", type: "submit", text: "Review catalog"}), result);
    form.addEventListener("submit", e => {e.preventDefault();
      if (d.reading) {result.replaceChildren(stateBox("error", "Files are still being read.", "Wait until the selected files are listed, then review again.")); return;}
      if (!d.files.length) {result.replaceChildren(stateBox("error", "Choose at least one reference .c5m file.")); return;}
      const args = {project: m.project.slug, expected_revision: m.revision, name: d.values.name.trim(), game_version: d.values.game_version.trim(),
        provenance: d.values.provenance.trim(), files: d.files.map(f => ({filename: f.filename, base64: f.base64}))};
      reviewWrite(m, d, form, result, "preview_catalog_import", args, "apply_catalog_import", args);});
    return stack(p("Builds a lookup catalog from vanilla-reference .c5m files: names, printed index numbers, explicit commands and their file positions. Duplicate names stay separate rows. Commented lines and game defaults are not imported.", "faint"), form);
  }
  function scoped(m, list) {
    if (scope() === "all") return list;
    const edges = m.edges.filter(e => ["setmaincom", "addstartcom", "addstartunits", "addunitrec", "addcomrec", "addmercrec"].includes(e.command));
    // Alternate forms follow the class of the unit they come from (form_classes, resolved by the server with cycle guards).
    return list.filter(o => {const cs = [...edges.filter(e => e.to?.index === o.index).map(e => String(e.from)), ...(o.form_classes || []).map(String)];
      return scope() === "none" ? !cs.length : cs.includes(scope());});
  }
  function overview(m, arg) {
    const units = scoped(m, m.objects.filter(o=>o.kind === "monster"));
    const vc=m.validation.counts,L=m.latest_export,art=artworkSummary(m);
    const rows=[{key:"validation",kind:!m.validation.static_ok?"err":vc.warning?"warn":"ok",label:"Validation",text:`${vc.error} errors · ${vc.warning} warnings · ${vc.unverified} unverified`,tab:"validation",action:"Validation report"},
      {key:"files",kind:m.counts.missing_assets?"err":"ok",label:"Referenced files",text:`${m.counts.missing_assets} missing or invalid files`,tab:"assets",action:"Assets"},
      {key:"artwork",kind:art.kind,label:"Artwork",text:art.text,href:route(m,"overview","artwork"),action:"Checklist"},
      {key:"export",kind:L?.error?"warn":!L?"info":L.revision===m.revision?"ok":"warn",label:"Latest export",text:L?`${short(L.revision)}${L.revision===m.revision?" · matches saved source":" · older revision"}`:"No exports yet.",tab:"export",action:"Open export"}];
    const attention=rows.some(r=>["err","warn"].includes(r.kind));
    const ready=el("section",{class:"panel readiness","aria-labelledby":"ready-h"},el("div",{class:"ready-head"},el("h3",{id:"ready-h",text:"Readiness"}),attention?badge("needs attention","err"):null),
      el("ul",{class:"ready-list"},rows.filter(r=>["err","warn"].includes(r.kind)||["export","artwork"].includes(r.key)).map(r=>el("li",{class:`ready-row is-${r.kind}`,"data-ready":r.key},
        ["err","warn"].includes(r.kind)?badge(r.kind==="err"?"Fix":"Check",r.kind):el("span",{"aria-hidden":"true"}),
        el("span",{class:"ready-label",text:r.label}),el("span",{class:"ready-text",text:r.text}),el("span",{class:"ready-action"},link(r.action,r.href||route(m,r.tab)))))),
      vc.error?details(`Validation errors (${vc.error})`,diagnostics(m,m.validation.diagnostics.filter(d=>d.severity==="error"))):null,
      artworkChecklist(m,arg==="artwork"));
    const tile = (n,t,tab) => el("a", {class:"tile", href:route(m,tab)}, el("div",{class:"n",text:n}), el("div",{class:"l",text:t}));
    return stack(m.mod_info.description ? p(m.mod_info.description.value,"prose muted") : null, ready,
      factionChecklist(m,isEmptyFaction(m)||arg==="design-checklist"), projectArtBrief(m,arg==="art-brief"),
      el("div", {class:"tiles"}, tile(units.length,"units","units"), tile(m.counts.class,"classes","classes"), tile(m.counts.weapon,"weapons","weapons"),
        tile(m.counts.ritual,"rituals","rituals"),tile(m.counts.assets,"asset files","assets")),
      catalogPanel(m,arg),
      arg === "settings" ? settings(m) : details("Project settings", settings(m)),
      details("Details", table(["Property","Value"], [["Source",m.provenance.path],["Revision",m.revision],["Encoding",m.provenance.encoding],["Manual",m.manual.version],["Source SHA-256",m.provenance.sha256]])));
  }
  function reference(m, ref) {
    if (!ref) return "—";
    if (ref.index !== undefined) {const o = m.objects.find(x=>x.index === ref.index); if(o) return objectLink(m,o);}
    if (ref.catalog !== undefined) return link(ref.name || ref.ref, route(m,"inspector","detail",ref.catalog));
    return el("span", {class:"faint", title:ref.note || "Unresolved reference", text:ref.name || ref.ref || ref.value || "Unknown"});
  }
  function objectLink(m, o) {
    const a = link(o.display, kindRoute(m,o));
    a.addEventListener("pointerenter", () => {if($("#keno-preview")?.dataset.pinned)return;clearTimeout(previewTimer);clearTimeout(previewHideTimer);previewTimer=setTimeout(()=>showPreview(a,m,o,false),350);});
    a.addEventListener("pointerleave", () => {clearTimeout(previewTimer); if (!$("#keno-preview")?.dataset.pinned) previewHideTimer=setTimeout(closePreview,150);});
    a.addEventListener("focus", () => {if(a.matches(":focus-visible")) showPreview(a,m,o,false);});
    a.addEventListener("blur", () => {if(!$("#keno-preview")?.dataset.pinned) closePreview();});
    return a;
  }
  function closePreview() {clearTimeout(previewTimer);clearTimeout(previewHideTimer);previewPlace=null;$("#keno-preview")?.remove();}
  function showPreview(anchor,m,o,pinned) {
    closePreview(); previewAnchor=anchor;
    const box=el("aside",{id:"keno-preview",class:"preview-pop unit-sheet",role:pinned?"dialog":"tooltip","aria-label":o.display,"data-pinned":pinned?"true":null},
      el("div",{class:"hover-head"},el("strong",{text:o.display}),pinned?btn("×",()=>{closePreview();anchor.focus();},"btn-ghost btn-small"):null),
      o.kind==="monster"?unitSheet(m,o,true):definitionBody(m,o),link("Open sheet",kindRoute(m,o)));
    document.body.append(box);
    box.style.position="fixed";box.style.zIndex="100";
    previewPlace=()=>{const rect=anchor.getBoundingClientRect();
      box.style.left=`${Math.max(8,Math.min(rect.right+12,innerWidth-Math.min(440,innerWidth-16)-8))}px`;
      box.style.top=`${Math.max(8,Math.min(rect.top,innerHeight-box.offsetHeight-8))}px`;};previewPlace();
    box.addEventListener("pointerenter",()=>clearTimeout(previewHideTimer));box.addEventListener("pointerleave",()=>{if(!pinned)previewHideTimer=setTimeout(closePreview,150);});
    box.style.maxWidth="min(440px, calc(100vw - 16px))";box.style.maxHeight="calc(100vh - 16px)";box.style.overflow="auto";
    if(pinned) {$("button",box)?.focus();box.addEventListener("keydown",e=>{if(e.key==="Escape"){e.preventDefault();closePreview();anchor.focus();}
      if(e.key==="Tab"){const stops=[...box.querySelectorAll("a,button")]; if(e.shiftKey&&document.activeElement===stops[0]||!e.shiftKey&&document.activeElement===stops.at(-1)){e.preventDefault();closePreview();anchor.focus();}}});}
  }
  document.addEventListener("pointerdown",e=>{if($("#keno-preview")&&!$("#keno-preview").contains(e.target)&&e.target!==previewAnchor)closePreview();
    const menu=$(".tab-more");if(menu&&!menu.contains(e.target)){$("ul",menu).hidden=true;$("button",menu).setAttribute("aria-expanded","false");}});
  document.addEventListener("keydown",e=>{if(e.key==="Escape")closePreview();});
  window.addEventListener("resize",()=>previewPlace?.());window.addEventListener("scroll",()=>previewPlace?.(),{capture:true,passive:true});
  function spriteFigure(m,o) {
    const sprites=o.view.sprites, available=[sprites.idle,sprites.attack].filter(s=>s?.url);
    if(!available.length) return el("figure",{class:"sheet-figure"},el("div",{class:"sheet-stage"},el("span",{class:"faint",text:sprites.inherited?"Inherited sprite":"No sprite"})));
    const image=el("img",{src:available[0].url,alt:`${o.display} sprite`,width:Math.min(available[0].width*2,256)});
    const stage=el("div",{class:"sheet-stage"},image), label=el("figcaption",{class:"sheet-cap",text:available[0].command});
    const controls=el("div",{class:"btn-row sheet-tools"},[1,2,3].map(zoom=>btn(`${zoom}×`,()=>{image.width=Math.min(available[0].width*zoom,512);},"btn-ghost btn-small")),
      available.length>1?btn("Idle / attack",()=>{const n=image.getAttribute("src")===available[0].url?1:0;image.src=available[n].url;label.textContent=available[n].command;},"btn-ghost btn-small"):null);
    return el("figure",{class:"sheet-figure"},stage,label,controls);
  }
  function unitSheet(m,o,compact=false) {
    const v=o.view, keys=[["hp","Hit points"],["str","Strength"],["armor","Armor"],["mr","Magic resist"],["mor","Morale"],["rank","Rank"]];
    const columns=[keys.slice(0,2),keys.slice(2,4),keys.slice(4)];
    const stats=el("div",{class:"sheet-stats"},columns.map(col=>el("dl",null,col.flatMap(([key,label])=>{
      const s=v.stats[key],value=key==="rank"?({"-1":"Back","0":"Mid","1":"Front"}[s.value]||s.value):s.value;
      return [el("dt",{text:label}),el("dd",{class:s.value==null?"unknown":s.source==="authored"?"mod":null,title:s.note||`${s.source}${s.line?` · line ${s.line}`:""}`,text:value??"?"})];}))));
    return el("section",{class:"unit-sheet"},el("header",{class:"sheet-head"},el("div",{class:"sheet-title"},el("h2",{id:compact?null:"detail-title",tabindex:compact?null:"-1",text:o.display}),el("span",{class:"sheet-type",text:o.new?"Custom unit":"Selected unit"})),
      el("div",{class:"sheet-sub",text:o.classes?.map(index=>m.objects.find(x=>x.index===index)?.display).filter(Boolean).join(" · ")||o.name})),
      el("div",{class:"sheet-body"},el("div",{class:"sheet-main"},stats,
        v.weapons.length?el("div",{class:"sheet-gear-wrap"},table(["Weapon","Damage"],v.weapons.map(w=>[[reference(m,w.weapon),w.note?el("div",{class:"faint",text:w.note}):null],w.dmg]))):p(`Weapons: ${v.weapons_status}`,"faint"),
        copiedAttacks(m,v.inherited_weapons,compact),
        el("p",{class:"sheet-abilities"},v.flags.map((f,i)=>[i?", ":"",el("span",{class:"mod",title:`line ${f.line}`,text:f.label})])),
        v.abilities?.length?(compact?p(`Abilities: ${v.abilities.map(a=>[a.label,...a.args].join(" ")).join(", ")}`,"faint"):
          table(["Ability","Value","Source"],v.abilities.map(a=>[[el("span",{class:"mod",text:a.label}),a.summary?el("div",{class:"faint",text:`${a.summary}${a.page?` (manual p.${a.page})`:""}`}):
            el("div",{class:"faint",text:a.status==="unknown"?"Not in the pinned manual; preserved verbatim.":a.status==="announced"?"Announced for CoE5 5.41, not in the pinned manual; preserved verbatim, not checked.":""}),a.note?el("div",{class:"faint",text:a.note}):null],a.args.join(" · ")||"—",sourceLink(m,a.line)]))):null,
        v.powers.length?p("Ritual power: "+v.powers.map(x=>x.name||x.value).join(", ")):null,
        v.spells.length?table(["Combat magic","Level"],v.spells.map(s=>[s.path_label||s.path,s.level])):null,
        unitForms(m,o,compact)),compact?null:spriteFigure(m,o)),
      p("Underlined values are authored in this mod. ? means unresolved or an unmodelled game default.","sheet-note"),
      compact?null:valueOrigins(m,o),
      v.description?el("div",{class:"sheet-descr"},v.description.split("\n").map(t=>p(t))):null,
      el("footer",{class:"sheet-foot"},sourceLink(m,o.line,`${m.provenance.file}:${o.line}`),v.donor?el("span",null," · Copies ",reference(m,v.donor)):null));
  }
  // Where each shown value comes from, using the server's resolver (Model.stat): authored here, copied from an explicit local
  // donor or a unique catalog row, or unresolved. Abilities and engine defaults are not resolved, and nothing unknown becomes zero.
  const STAT_NAMES=[["hp","Hit points"],["str","Strength"],["armor","Armor"],["mr","Magic resist"],["mor","Morale"],["rank","Rank"]];
  function statOrigin(m,s){
    if(s.source==="authored")return ["Authored here",s.line?[" · ",sourceLink(m,s.line)]:null];
    if(s.source==="donor")return [`Copied from ${s.via}`,s.line?[" · donor ",sourceLink(m,s.line)]:null];
    if(s.source==="catalog")return [`Local catalog${s.via?`, copied from ${s.via}`:""}`];
    if(s.source==="default")return ["Game default (not modelled)"];
    return [s.via?`Unresolved copy from ${s.via}`:"Unresolved"];
  }
  function valueOrigins(m,o){
    const v=o.view,sp=v.sprites,copies=(v.resets||[]).filter(r=>["copystats","copyspr"].includes(r.command));
    const value=(k,s)=>el("span",{class:s.value==null?"unknown":s.source==="authored"?"mod":null,text:s.value==null?"?":k==="rank"?({"-1":"Back","0":"Mid","1":"Front"}[s.value]||s.value):s.value});
    const rows=STAT_NAMES.map(([k,label])=>{const s=v.stats[k];return [label,value(k,s),statOrigin(m,s),s.note||"—"];});
    const frame=(f,label)=>f?[label,f.path,["Authored here · ",sourceLink(m,f.line)],f.status==="ok"?"—":`File ${f.status||"missing"}`]:null;
    rows.push(frame(sp.idle,"Idle sprite")||["Idle sprite",el("span",{class:"unknown",text:"?"}),sp.inherited?[`Inherited via ${sp.inherited.command} ${sp.inherited.ref||""} · `,sourceLink(m,sp.inherited.line)]:"Not set","The inherited image itself is not resolved."]);
    rows.push(frame(sp.attack,"Attack sprite")||["Attack sprite",el("span",{class:"unknown",text:"?"}),sp.idle?"Not set: spr1 is shown for attacks":"Not set","—"]);
    rows.push(["Attacks",v.weapons_status,v.weapons_status==="authored"?"Authored here":v.weapons_status==="inherited"||v.weapons_status==="partial"?"Copied attacks listed above":v.weapons_status,
      v.inherited_weapons?.note||"—"]);
    rows.push(["Abilities",`${(v.flags?.length||0)+(v.abilities?.length||0)} explicit`,"Authored here",v.donor?"Abilities copied through copystats are not resolved; only explicit lines are listed.":"—"]);
    const body=stack(p(v.donor?"This unit copies another definition. Values below say whether they are authored here, copied from an explicit donor in this mod, read from a unique catalog row, or unresolved. ? is unknown, never zero.":
        "Values below are authored here or unresolved. ? is unknown, never zero; game defaults are not modelled.","faint"),
      table(["Field","Value","Origin","Note"],rows),
      v.resets?.length?stack(el("h4",{text:"Copy and reset order"}),p("Later commands apply after earlier ones. A copy or clear command can replace values set above it; its effect on abilities is not simulated.","faint"),
        table(["Line","Command","Target"],v.resets.map(r=>[sourceLink(m,r.line,String(r.line)),r.label,r.ref||"—"]))):null);
    return el("details",{class:"tech"},el("summary",{text:copies.length?`Inheritance and value origins (copies ${copies.map(c=>c.ref).join(", ")})`:"Value origins"}),body);
  }
  // Attacks a copystats donor states explicitly; unresolved or partial chains say so instead of guessing.
  function copiedAttacks(m,inh,compact){
    if(!inh)return null;
    if(inh.status==="cleared"||!inh.weapons?.length)return p(`Copied attacks: ${inh.status==="cleared"?"cleared":`not resolved (${inh.via||"donor"})`}. ${inh.note||""}`,"faint");
    const title=`Copied attacks from ${inh.via}${inh.status==="resolved"?"":` (${inh.status})`}`;
    if(compact)return p(`${title}: ${inh.weapons.map(w=>`${w.ref} ${w.dmg}`).join(", ")}`,"faint");
    return stack(table([title,"Damage","Stated by"],inh.weapons.map(w=>[reference(m,w.weapon),w.dmg,w.source==="catalog"?"Local catalog":w.line?[w.source," · ",sourceLink(m,w.line)]:w.source])),p(inh.note,"faint"));
  }
  function unitForms(m,o,compact){
    const forms=o.view.forms||[],of=(o.form_of||[]).map(i=>m.objects.find(x=>x.index===i)).filter(Boolean);
    if(!forms.length&&!of.length)return null;
    if(compact)return p(`Forms: ${[...forms.map(f=>`${f.relation} ${f.target.name||"?"}`),...of.map(x=>`form of ${x.display}`)].join("; ")}`,"faint");
    return stack(forms.length?table(["Alternate form","Relationship","Source"],forms.map(f=>[[reference(m,f.target),f.target.note?el("div",{class:"faint",text:f.target.note}):null],f.relation,sourceLink(m,f.line)])):null,
      of.length?el("p",null,"Alternate form of ",of.map((x,i)=>[i?", ":"",objectLink(m,x)]),"."):null);
  }
  // Read-only comparison against chosen local units or catalog rows, never a draft. The chosen references live in the
  // address (?refs=u:3,cat:12; the older single ?ref=cat:N is still read), so reload, back and shared links reproduce it.
  const refToken=r=>r.object_index!==undefined?`u:${r.object_index}`:`cat:${r.catalog_index}`;
  const linkedRefs=()=>{const q=query();return [...new Set([...(q.get("refs")||"").split(","),q.get("ref")||""].map(x=>x.trim()).filter(Boolean))];};
  const shortOrigin=s=>s.source==="authored"?(s.line?`line ${s.line}`:"authored"):s.source==="donor"?`from ${s.via}`:s.source==="catalog"?"catalog":s.source==="default"?"default not modelled":"unresolved";
  function compareUnits(m,o){
    const key=`${m.project.slug}:compare:${o.index}`,c=state.filters.get(key)||{refs:[],invalid:[],result:null,resultFor:"",linked:"",zoom:2};state.filters.set(key,c);
    // Both local definitions and catalog rows are positional; discard old choices rather than infer identity by name.
    if(c.rev&&c.rev!==pinOf(m)){c.refs=[];c.invalid=[];c.result=null;c.resultFor="";c.linked="";}
    c.rev=pinOf(m);
    for(const r of c.refs)if(r.object_index!==undefined)r.label=m.objects.find(x=>x.index===r.object_index)?.display||r.label;
    const box=el("div",{"aria-live":"polite"}),chips=el("ul",{class:"plain-list chips","aria-label":"Chosen references"}),hits=el("div"),recovery=el("div"),limit=el("p",{class:"field-meta",role:"status"});
    const others=m.objects.filter(x=>x.kind==="monster"&&x.index!==o.index),tokens=linkedRefs();
    const current=()=>c.refs.map(refToken).join(",");
    // Keep the address in step with the chosen references without rebuilding the page.
    function syncUrl(){const q=new URLSearchParams(query());q.delete("ref");if(c.refs.length)q.set("refs",current());else q.delete("refs");
      history.replaceState(null,"",path(...parts())+`?${q}`);c.linked=current();}
    const local=select("compare-local",[["","Choose a unit of this project"],...others.map(x=>[String(x.index),`${x.display} (line ${x.line})`])]);
    let compareTicket=0;
    // A changed selection invalidates both the visible result and any earlier response still in flight.
    function invalidateComparison(){compareTicket++;c.result=null;c.resultFor="";run.disabled=false;box.replaceChildren();}
    const addRef=r=>{if(c.refs.length>=4){limit.textContent="Compare at most four references; remove one first.";return;}limit.textContent="";
      if(!c.refs.some(x=>refToken(x)===refToken(r))){c.refs.push(r);invalidateComparison();}syncUrl();showChips();};
    function showChips(){chips.replaceChildren(...c.refs.map((r,i)=>{const b=btn(`${r.label} ×`,()=>{c.refs.splice(i,1);invalidateComparison();limit.textContent="";syncUrl();showChips();},"btn-small btn-ghost");
      b.setAttribute("aria-label",`Remove ${r.label} from comparison`);return el("li",null,b);}));
      if(!c.refs.length)chips.append(el("li",{class:"faint",text:"No references chosen."}));}
    function showRecovery(){recovery.replaceChildren(c.invalid.length?stack(stateBox("warn","Some references in this link cannot be compared.","They were not used. Remove them to compare the rest, or start again."),
      el("ul",null,c.invalid.map(x=>el("li",null,el("span",{class:"mono",text:x.token})," — ",x.reason))),
      el("div",{class:"btn-row"},btn(c.refs.length?"Remove them and compare the rest":"Remove them",()=>{c.invalid=[];syncUrl();showRecovery();if(c.refs.length)runCompare();},"btn-small"),
        btn("Clear comparison",clearAll,"btn-small btn-ghost"))):"");}
    function clearAll(){c.refs=[];c.invalid=[];invalidateComparison();syncUrl();showChips();showRecovery();local.focus();}
    // Turn address tokens into references; local ones are checked against this model, catalog ones against the catalog.
    async function fromLink(){
      const refs=[],invalidRefs=[],pending=[];
      tokens.forEach((t,i)=>{let mt;
        if(i>=4)invalidRefs.push({token:t,reason:"More than four references."});
        else if((mt=t.match(/^u:(\d+)$/))){const x=others.find(y=>y.index===Number(mt[1]));x?refs.push({object_index:x.index,label:x.display}):
          invalidRefs.push({token:t,reason:Number(mt[1])===o.index?"This is the unit being compared.":"Not a unit of this project's saved revision."});}
        else if((mt=t.match(/^cat:(\d+)$/))){const r={catalog_index:Number(mt[1]),label:`Catalog row ${mt[1]}`};refs.push(r);pending.push([t,r]);}
        else invalidRefs.push({token:t,reason:"Not a recognised reference (use u:<unit> or cat:<catalog row>)."});});
      // The link counts as applied only once its catalog rows are checked, so a page rebuilt meanwhile checks them again.
      c.refs=refs;c.invalid=invalidRefs;c.linked=pending.length?"":tokens.join(",");c.result=null;showChips();showRecovery();
      // One ticket for this check: a changed selection or a newer page makes both answers and refusals of it stale.
      const request=++compareTicket,fresh=()=>request===compareTicket&&box.isConnected;
      if(pending.length)box.replaceChildren(stateBox("loading","Checking catalog references…"));
      // Each catalog row is read once (a read, never a write); a refusal or failure only lists that reference as unusable.
      await Promise.all(pending.map(async([t,r])=>{try{const row=(await get(`${base(m)}/catalog/${r.catalog_index}`)).row;if(!fresh())return;
        if(row?.kind!=="monster")throw failure("not_monster","That catalog row is not a monster.");r.label=`${row.name} (catalog)`;}
        catch(e){if(!fresh())return;c.refs=c.refs.filter(x=>x!==r);
          c.invalid.push({token:t,reason:e.code==="not_found"?"Not a row of the configured catalog (it may be missing or changed).":
            ["network_error","bad_response"].includes(e.code)?`${e.message} It could not be checked; use Clear comparison, or reload the page once the server answers.`:e.message});}}));
      if(!fresh())return;
      c.linked=tokens.join(",");box.replaceChildren();showChips();showRecovery();if(c.refs.length&&!c.invalid.length)runCompare();
    }
    const search=input("compare-catalog","","search");search.placeholder="Search catalog monsters";search.setAttribute("aria-label","Search catalog monsters");
    let timer,ticket=0;search.addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(async()=>{const mine=++ticket;if(!search.value.trim()){hits.replaceChildren();return;}
      try{const r=await get(`${base(m)}/catalog?${new URLSearchParams({q:search.value.trim(),kind:"monster",per:"10"})}`);if(mine!==ticket)return;
        hits.replaceChildren(!r.catalog.available?p(r.catalog.note,"faint"):r.rows.length?el("ul",{class:"plain-list"},r.rows.map(row=>el("li",null,
          btn(`Add ${row.name}${row.name_count>1?` (duplicate ${row.name_ordinal+1} of ${row.name_count})`:""}`,()=>addRef({catalog_index:row.index,label:`${row.name} (catalog)`}),"btn-small btn-ghost"),
          row.source_file?el("span",{class:"faint",text:` ${row.source_file}:${row.source_line}`}):null))):p("No catalog matches.","faint"));}catch(e){if(mine===ticket)hits.replaceChildren(errorBox(e));}},300);});
    const run=btn("Compare",()=>runCompare());
    async function runCompare(){
      if(!c.refs.length){box.replaceChildren(stateBox("error","Choose at least one reference.","Add a unit of this project or a catalog monster above."));return;}
      run.disabled=true;box.replaceChildren(stateBox("loading","Comparing…"));syncUrl();const forKey=`${m.revision}|${current()}`,request=++compareTicket;
      try{const result=await api("compare_units",{project:m.project.slug,object_index:o.index,references:c.refs.map(({label,...r})=>r)});if(request!==compareTicket||forKey!==`${m.revision}|${current()}`)return;if(result.revision!==m.revision)throw failure("stale_revision","The saved project changed. Reload it and choose the comparison again.");c.result=result;c.resultFor=forKey;show();}
      catch(e){if(request!==compareTicket)return;box.replaceChildren(stack(errorBox(e,e.code==="stale_revision"?()=>{state.models.delete(m.project.slug);render();}:null),["bad_reference","not_found"].includes(e.code)?p("A reference is no longer available in the saved project or catalog. Remove it from the chosen references, or clear the comparison.","faint"):null,
        el("div",{class:"btn-row"},btn("Clear comparison",clearAll,"btn-small btn-ghost"))));}
      finally{if(request===compareTicket)run.disabled=false;}
    }
    function cell(s){return el("div",null,el("span",{class:s.value==null?"unknown":s.source==="authored"?"mod":null,title:s.note||null,text:s.value??"?"}),el("div",{class:"faint",text:shortOrigin(s)}));}
    function sprites(col){
      if(col.type==="catalog")return el("span",{class:"faint",text:col.sprite_note||"No catalog image."});
      const sp=col.sprites||{},frame=(f,pose)=>f?.url?artFigure(pose,zoomImg(f.url,`${col.name} ${pose.toLowerCase()} frame`,f.width,()=>c.zoom||2),f.width?`${f.width}×${f.height}`:null):
        artFigure(pose,missingArt(f?`File ${f.status||"missing"}`:pose==="Attack"&&sp.idle?"Not set: idle shown for attacks":sp.inherited?`Inherited via ${sp.inherited.command} (not resolved)`:"Not set"));
      return el("div",{class:"art-pair"},frame(sp.idle,"Idle"),frame(sp.attack,"Attack"));
    }
    const attackList=col=>col.attacks.length?el("ul",{class:"plain-list"},col.attacks.map(a=>el("li",null,`${a.command} ${a.dmg??"?"} ${a.weapon??"?"}`,
      el("span",{class:"faint"}," · ",a.source==="authored"&&a.line?sourceLink(m,a.line):a.source)))):el("span",{class:"faint",text:`None stated (${col.attacks_status})`});
    const GROUP={unit:"troop",commander:"commander",mercenary:"mercenary"};
    const recruitList=col=>el("div",null,col.recruitment.rows.length?el("ul",{class:"plain-list"},col.recruitment.rows.map(r=>el("li",null,
      `${r.cls}: ${GROUP[r.group]||r.group} · chance ${r.chance??"?"}%${r.group==="commander"?"":` · count ${r.count??"?"}`} · gold ${r.gold??"?"} (die ${r.gold_die??"?"}) · iron ${r.iron??"?"}`,
      r.extra_costs?.length?` · extra ${r.extra_costs.map(x=>`${x.amount??"?"} ${x.resource||x.raw}`).join(", ")}`:"",
      el("span",{class:"faint"}," · ",r.source==="authored"?sourceLink(m,r.line):r.provenance||"catalog")))):el("span",{class:"faint",text:"No recruitment rows found."}),
      p(col.recruitment.note,"faint"));
    const ritualList=col=>el("div",null,col.rituals.schools.length?el("ul",{class:"plain-list"},col.rituals.schools.map(s=>el("li",{class:s.status==="unresolved"?"unknown":null},
      `${s.school}${s.all?" (all rituals)":""}`,s.line?el("span",{class:"faint"}," · ",sourceLink(m,s.line)):null,s.status==="unresolved"?el("span",{class:"faint",text:` · unresolved${s.note?`: ${s.note}`:""}`}):null))):
      el("span",{class:"faint",text:"No power or allrit stated."}),p(col.rituals.note,"faint"));
    const source=col=>col.type==="catalog"?el("div",null,link(col.provenance,route(m,"inspector","detail",col.catalog_index)),el("div",{class:"faint",text:`game ${col.game_version}${col.catalog_source==="snapshot"?" · private snapshot":""}`})):
      el("div",null,objectLink(m,m.objects.find(x=>x.index===col.index)),el("div",{class:"faint",text:col.provenance}));
    function show(){const r=c.result;if(!r)return;const cols=r.columns;
      const row=(label,cells)=>el("tr",null,el("th",{scope:"row",text:label}),cells.map(x=>el("td",null,x)));
      const grid=el("div",{class:"table-wrap",tabindex:"0",role:"region","aria-label":"Comparison table (scrolls sideways on narrow screens)"},el("table",{class:"data"},
        el("caption",{text:`${o.display} beside ${cols.length-1} reference${cols.length>2?"s":""}. Unknown values show ? and are not compared.`}),
        el("thead",null,el("tr",null,el("th",{scope:"col",text:"Value"}),cols.map((col,i)=>el("th",{scope:"col"},stack(el("strong",{text:col.name}),
          el("div",{class:"faint",text:i===0?"This unit":col.type==="catalog"?`Catalog · game ${col.game_version}`:`${col.new?"Custom":"Selected"} unit`})))))),
        el("tbody",null,row("Images",cols.map(sprites)),...r.rows.map(x=>row(x.label,x.cells.map(cell))),row("Attacks",cols.map(attackList)),
          row("Explicit abilities",cols.map(col=>col.abilities.length?col.abilities.join(", "):el("span",{class:"faint",text:"None explicit"}))),
          row("Recruitment",cols.map(recruitList)),row("Ritual access",cols.map(ritualList)),row("Source",cols.map(source)))));
      box.replaceChildren(stack(zoomControl(c,()=>rezoom(box,c.zoom)),grid,
        ...cols.flatMap(col=>(col.warnings||[]).map(w=>stateBox("warn",`${col.name}: check provenance`,w))),
        r.differences.length?panel("Source-backed differences",el("ul",null,r.differences.map(d=>el("li",{text:Array.isArray(d.unit)?`${d.label} vs ${d.reference}: only this unit ${d.unit.join(", ")||"—"}; only ${d.reference} ${d.other.join(", ")||"—"}`:
          `${d.label}: ${d.unit} here vs ${d.other} in ${d.reference}`})))):p("No differences among the values known on both sides.","faint"),
        r.unresolved.length?p(`Not compared (unknown on one side): ${r.unresolved.map(u=>`${u.key} vs ${u.reference}`).join(", ")}`,"faint"):null,
        el("ul",{class:"art-notes"},r.notes.map(n=>el("li",{text:n})))));}
    showChips();showRecovery();
    if(tokens.length&&tokens.join(",")!==c.linked)fromLink();
    else{if(c.refs.length&&!tokens.length)syncUrl();if(c.result&&c.resultFor===`${m.revision}|${current()}`)show();else if(c.refs.length&&!c.invalid.length&&c.linked)runCompare();}
    return el("details",{class:"tech",open:tokens.length||c.refs.length?true:null},el("summary",{text:"Compare with references"}),
      p("Read-only. Values keep their source: authored here, a local donor, or the catalog with its game version. Unknown values stay unknown. The address keeps your chosen references, so you can reload or share the link.","faint"),
      el("div",{class:"btn-row"},field("Unit of this project",local),btn("Add unit",()=>{const x=others.find(y=>String(y.index)===local.value);if(x)addRef({object_index:x.index,label:x.display});},"btn-small")),
      field("Catalog monster",search),hits,chips,limit,recovery,run,box);
  }
  function relations(m,o) {
    const used=(o.used_by||[]).map(e=>[objectLink(m,m.objects.find(x=>x.index===e.from)),e.relation,sourceLink(m,e.line)]);
    const uses=(o.uses||[]).map(e=>[reference(m,e.to),e.relation,sourceLink(m,e.line)]);
    return used.length||uses.length?details("Related content",used.length?panel("Used by",table(["Definition","Relationship","Source"],used)):null,
      uses.length?panel("Uses",table(["Definition","Relationship","Source"],uses)):null):null;
  }
  function definitionBody(m,o) {
    const v=o.view || {};
    if(o.kind==="class") return stack(v.classdescr?p(v.classdescr.value,"prose"):null,v.classabdescr?p(v.classabdescr.value,"prose"):null,
      table(["Setting","Value"],["hometerr","startplane","createcit","goldbonus","ironbonus"].filter(k=>v[k]).map(k=>[state.meta.forms.class.fields.find(f=>f.key===k)?.label||k,
        v[k].target?reference(m,v[k].target):v[k].meaning||v[k].value])),
      panel("Starting forces",v.main_commander?el("p",null,"Main commander: ",reference(m,v.main_commander)):null,
        v.army.map(a=>stack(a.commander?el("h4",null,reference(m,a.commander)):p("Before addstartcom (squad not modelled)"),
          table(["Unit","Count"],a.units.map(u=>[reference(m,u.monster),u.count]))))),
      ...Object.entries(v.recruitment).map(([k,rs])=>rs.length?panel(k==="units"?"Recruitable units":k==="commanders"?"Recruitable commanders":"Mercenary recruits",
        table(k==="commanders"?["Unit","Chance %","Gold","Gold die","Iron"]:["Unit","Chance %","Count","Gold","Gold die","Iron"],
          rs.map(r=>[reference(m,r.monster),r.chance,...(k==="commanders"?[]:[r.count??"?"]),r.gold,r.gold_die,r.iron]))):null),
      link("Open in Design",path("p",m.project.slug,"design")+`?c=${o.index}`,"btn btn-small btn-ghost"));
    if(o.kind==="weapon") return stack(table(["Property","Value"],Object.entries(v.fields).map(([k,f])=>[f.label||k,
      el("span",{class:"mod",title:`line ${f.line}`,text:f.meaning?`${f.meaning} (${f.value})`:f.value})])),p(v.defaults,"faint"));
    if(o.kind==="ritual") return stack(el("p",null,"School: ",reference(m,v.school)),p(`Level ${v.level?.value??"?"}${v.free?" · always known":""}`),
      table(["Resource","Cost"],v.costs.map(c=>[c.label||c.resource,c.amount])),v.strings.length?panel(v.summoning?"Summons":"Ritual strings",v.strings.map(s=>stack(
        p(s.text,"mono"),v.summoning?el("p",null,s.parts.map((t,i)=>[i?" + ":"",t.count?`${t.count} × `:"",reference(m,t.target),t.commander?" (commander)":""])):null))):null,p(v.string_note,"faint"));
    if(o.kind==="school") return stack(p("Rituals and units refer to this school by their order in the source."),
      table(["Ritual","Level"],m.objects.filter(x=>x.kind==="ritual"&&x.view.school?.index===o.index).map(r=>[objectLink(m,r),r.view.level?.value??"?"])));
    if(o.kind==="terrain") return stack(v.sprite?.url?el("img",{class:"pixel",src:v.sprite.url,alt:o.display}):null,
      p(`${v.custom?"Custom terrain":"Existing terrain"} ${v.number}${v.citadel?" · citadel":""}`),table(["Property","Value"],[["Gold",v.gold?.value??"?"],["Iron",v.iron?.value??"?"]]),p(v.note,"faint"));
    if(o.kind==="item") return stack(v.sprite?.url?el("img",{class:"pixel",src:v.sprite.url,alt:o.display}):null,p(v.descr||""),p(`Type: ${v.type?.meaning||v.type?.value||"not set"}`));
    if(o.kind==="event") return stack(p(`${v.triggers.length} triggers · ${v.actions.length} actions · ${v.closed?"closed":"missing endevent"}`),
      table(["Command","Arguments","Source"],o.statements.filter(s=>!s.opener).map(s=>[s.label,s.args.join(" · "),sourceLink(m,s.line)])));
    return table(["Command","Value","Source"],o.statements.filter(s=>!s.opener).map(s=>[s.label,s.args.join(" · "),sourceLink(m,s.line)]));
  }
  // Browse/Edit switch (the reference's sectionModes): leaving the form keeps its draft, and Edit returns to that same form.
  function sectionModes(m,kind,o,mode,...extra) {
    const tab=kinds[kind][2],creating=mode==="new",d=state.drafts.get(`${m.project.slug}:edit:${kind}:${o?o.index:""}`);
    const browse=o&&kind!=="global"?(kind==="class"&&scope()===String(o.index)?route(m,tab):kindRoute(m,o)):kind==="global"?route(m,"overview"):route(m,tab);
    const item=(id,on,href,text)=>el("a",{id,class:"btn btn-small",href,"aria-current":on?"page":null},text);
    return el("div",{class:"btn-row section-modes"},el("nav",{class:"btn-row seg mode-switch","aria-label":`${kinds[kind][1]} view`},
      item("mode-browse",mode==="browse",browse,"Browse"),creating?item("mode-edit",true,location.hash,`New ${kinds[kind][1].toLowerCase()}`):
        item("mode-edit",mode==="edit",route(m,tab,"edit",o.index),"Edit")),
      !creating&&mode==="browse"&&d?.dirty?badge("unsaved edit draft","warn"):null,...extra);
  }
  function detailView(m,o) {
    // Removal has no form input, so reviewing it is not a draft; one review box lives inside the disclosure.
    // After removal the position names another definition (or none), so the save returns to the list instead.
    const removal={key:`${m.project.slug}:remove:${o.index}`,slug:m.project.slug,label:`Remove ${o.display}`,afterSave:o.kind==="class"?path("p",m.project.slug,"classes")+"?c=all":route(m,kinds[o.kind][2])},removalBox=el("div");
    const removalForm=el("div",{class:"stack"},p("The entire block is reviewed before removal. Referenced definitions cannot be removed.","faint"),
      btn("Review removal…",()=>{const args={project:m.project.slug,expected_revision:m.revision,object_index:o.index,changes:[],mode:"delete"};
        reviewWrite(m,removal,removalForm,removalBox,"preview_block_edit",args,"apply_block_edit",args);},"btn-ghost btn-small"),removalBox);
    return stack(sectionModes(m,o.kind,o,"browse",btn("Preview",e=>showPreview(e.currentTarget,m,o,true),"btn-ghost btn-small"),
      link("Duplicate",route(m,kinds[o.kind][2],"new",o.index),"btn btn-ghost btn-small")),
      // The sheet or panel heading is the focus target when a definition is selected (render: focusDetail).
      o.kind==="monster"?unitSheet(m,o):el("section",{class:"panel"},el("h3",{id:"detail-title",tabindex:"-1",text:o.display}),definitionBody(m,o)),relations(m,o),
      o.kind==="monster"?compareUnits(m,o):null,
      o.kind==="monster"?artEditor(m,o):null,
      details("Remove definition",removalForm),
      o.diagnostics.length?details(`Diagnostics (${o.diagnostics.length})`,diagnostics(m,o.diagnostics)):null,
      details("Authored commands",table(["Command","Arguments","Source"],o.statements.map(s=>[s.command,s.args.join(" · "),sourceLink(m,s.line)]))),
      details("Source",el("pre",{class:"code",text:o.text})),details("JSON",el("pre",{class:"code",text:JSON.stringify(o,null,2)})));
  }
  function contentList(m,kind,id) {
    const pool=kind==="monster"?scoped(m,m.objects.filter(o=>o.kind===kind)):m.objects.filter(o=>o.kind===kind), tab=kinds[kind][2];
    const selected=m.objects.find(o=>String(o.index)===String(id)&&o.kind===kind);
    const actions=el("div",{class:"btn-row"},link(`New ${kinds[kind][1].toLowerCase()}`,route(m,tab,"new"),"btn"));
    if(!pool.length&&!selected) return stack(actions,kind==="monster"&&scope()!=="all"?
      stateBox("empty","No units in this class selection.","Create a unit, or choose All classes in the Class filter above."):
      stateBox("empty",`No ${kinds[kind][0].toLowerCase()} yet.`,`Create one with New ${kinds[kind][1].toLowerCase()}, or import a mod that defines them.`));
    const f=state.filters.get(`${m.project.slug}:${kind}`)||{q:"",role:"all"};state.filters.set(`${m.project.slug}:${kind}`,f);
    const search=input("content-search",f.q,"search");search.placeholder=`Search ${kinds[kind][0].toLowerCase()}  ( / )`;search.setAttribute("aria-label",search.placeholder);
    const status=p("","faint"), list=el("ul",{class:"unit-list","aria-label":kinds[kind][0]});
    function fill(){const rows=pool.filter(o=>`${o.display} ${o.name}`.toLowerCase().includes(f.q.toLowerCase())&&(kind!=="monster"||f.role==="all"||o.role===f.role));
      const row=o=>el("li",null,el("a",{class:"unit-item",href:kindRoute(m,o),"aria-current":o===selected?"true":null},
        el("span",{class:"thumb"},o.view?.sprites?.idle?.url?el("img",{src:o.view.sprites.idle.url,alt:"",loading:"lazy"}):null),
        el("span",null,el("div",{class:"nm",text:o.display}),el("div",{class:"sub",text:`${o.new?"Custom":"Selected"} · line ${o.line}`}))));
      list.replaceChildren();
      if(kind==="monster")for(const [role,label]of [["commander","Commanders"],["troop","Troops"],["summon","Summons"],["form","Alternate forms"],["unassigned","Not tied to a class"]]){
        const group=rows.filter(o=>o.role===role);if(group.length)list.append(el("li",{class:"group-label",text:`${label} (${group.length})`}),...group.map(row));
      }else list.append(...rows.map(row));
      if(!rows.length)list.append(el("li",null,stateBox("empty","No matches.","Clear the search.")));status.textContent=`${rows.length} of ${pool.length} ${kinds[kind][0].toLowerCase()}`;}
    search.addEventListener("input",()=>{f.q=search.value;fill();});search.addEventListener("keydown",e=>{if(e.key==="Escape"){search.value="";f.q="";fill();}if(e.key==="ArrowDown"){e.preventDefault();$("a",list)?.focus();}});
    list.addEventListener("keydown",e=>{if(!["ArrowUp","ArrowDown"].includes(e.key))return;const links=[...list.querySelectorAll("a")],i=links.indexOf(document.activeElement);if(i<0)return;e.preventDefault();
      if(i===0&&e.key==="ArrowUp")search.focus();else links[Math.max(0,Math.min(links.length-1,i+(e.key==="ArrowDown"?1:-1)))].focus();});fill();
    const role=kind==="monster"?select("role",[["all","All roles"],["commander","Commanders"],["troop","Troops"],["summon","Summons"],["form","Alternate forms"],["unassigned","Unassigned"]],f.role):null;
    role?.setAttribute("aria-label","Unit role");
    role?.addEventListener("change",()=>{f.role=role.value;fill();});
    if(kind!=="monster"&&!selected){const cards=el("div",{class:"grid-2 spell-grid"});
      const fillCards=()=>{const rows=pool.filter(o=>o.display.toLowerCase().includes(search.value.toLowerCase()));cards.replaceChildren(...rows.map(o=>
        el("article",{class:"item-card"},el("div",{class:"item-card-head"},el("div",null,el("h2",null,objectLink(m,o)),p(`${o.new?"Custom":"Selected"} ${o.kind_label.toLowerCase()}`,"faint"))),
          definitionBody(m,o),el("div",{class:"btn-row"},link("Open",kindRoute(m,o),"btn btn-small"),link("Edit",route(m,tab,"edit",o.index),"btn btn-small btn-ghost")))));};
      search.addEventListener("input",fillCards);fillCards();return stack(actions,el("div",{class:"unit-filter"},search),cards);}
    // Below 1100px (CSS) a selected item collapses the roster so the sheet comes first; wider windows always show it.
    const open=!selected||rosterOpen,name=kinds[kind][0].toLowerCase(),body=el("div",{class:"roster-body",id:"unit-roster"},el("div",{class:"unit-filter"},search,role),status,list);
    const label=()=>rosterOpen?`Hide ${name} list`:`Show ${name} list (${pool.length})`;
    const toggle=selected?btn(label(),()=>{rosterOpen=pane.classList.contains("roster-collapsed");pane.classList.toggle("roster-collapsed",!rosterOpen);
      toggle.setAttribute("aria-expanded",String(rosterOpen));toggle.textContent=label();},"btn-small btn-ghost roster-toggle"):null;
    toggle?.setAttribute("aria-controls","unit-roster");toggle?.setAttribute("aria-expanded",String(open));
    const pane=el("aside",{class:`panel unit-pane${open?"":" roster-collapsed"}`,"aria-label":`${kinds[kind][0]} list`},toggle,body);
    const split=el("div",{class:"split"},pane,el("article",{id:kind==="monster"?"unit-detail":null,class:"sheet-view"},selected?detailView(m,selected):stateBox("empty",`Choose a ${kinds[kind][1].toLowerCase()}.`)));
    return stack(actions,split);
  }
  // Review is inline, with the form draft retained through failures and route changes.
  async function reviewWrite(m,d,form,box,previewOp,previewArgs,applyOp,applyArgs) {
    if(d.busy)return;d.busy=true;box.replaceChildren(stateBox("loading","Preparing review…"));
    const trigger=document.activeElement;
    const controls=[...form.querySelectorAll("input,textarea,select,button")].filter(c=>!box.contains(c));
    const disabled=controls.map(c=>c.disabled);
    const unlock=()=>controls.forEach((c,i)=>{c.disabled=disabled[i];});
    controls.forEach(c=>{c.disabled=true;});
    try {
      const result=await post(previewOp,previewArgs);if(!result.diff&&!result.record){unlock();box.replaceChildren(stateBox("ok","Nothing to save."));return;}
      const back=()=>{box.replaceChildren();unlock();trigger?.focus();};
      const save=btn("Save reviewed change",async()=>{
        if(d.busy)return;d.busy=true;save.disabled=true;
        try{const r=await post(applyOp,applyArgs);recordReceipt(m,r,d.label||"Saved change");state.drafts.delete(d.key);state.models.delete(m.project.slug);
          if(d.afterSave)history.replaceState(null,"",d.afterSave);
          else if(applyOp === "apply_fields" || (applyOp === "apply_block_edit" && (applyArgs.mode || "edit") === "edit")) {
            const q=query();if(q.has("rev")){q.set("rev",r.revision.slice(0,16));history.replaceState(null,"",path(...parts())+`?${q}`);}
          }
          await reloadProjects();toast("Saved reviewed change.");await render();}
        // A field error from the save unlocks the form so the named control can be corrected in place.
        catch(e){if(fieldControl(form,e.details?.field,e.message))unlock();writeFailure(e,m,d,box,()=>{unlock();box.replaceChildren();trigger?.focus();},form);save.disabled=false;}finally{d.busy=false;}
      });
      const changes=result.changes?.length?table(["Change","Before","After"],result.changes.map(c=>[[`${c.op}: ${c.command||""}`,c.block?el("div",{class:"faint",text:`in ${c.block} (line ${c.block_line})`}):null,c.note?el("div",{class:"faint",text:c.note}):null],c.before||"—",c.after||"—"])):null;
      const record=result.record?table(["Field","Value"],[["Category",result.record.category_label],["Summary",result.record.summary],["Details",result.record.details||"—"],
        ["Reference",result.record.reference||"—"],...referenceRows(result.record.references),...observationRows(result.record.observation),["Revision",result.record.revision],["Engine verified","No (recorded observations never verify game behavior)"]]):null;
      box.replaceChildren(panel("Review changes",changes,record,
        result.compatibility_impact?compatImpact(m,result.compatibility_impact):null,
        result.form_changes?.length?stateBox("error","Alternate-form targets move",result.form_changes.map(f=>`${f.unit} ${f.command}: ${f.before||"unresolved"} → ${f.after||"unresolved"}`).join("; ")+". Form commands count new monsters in source order."):null,
        result.frames?artReview(m,result,d):result.art_preview?el("div",{class:"sprite-box"},el("img",{src:`data:image/png;base64,${result.art_preview}`,alt:"Reviewed artwork preview"})):null,
        result.assets?table(["Asset","Bytes","SHA-256"],result.assets.map(a=>[a.path,a.bytes,short(a.sha256)])):null,
        result.sources?stack(p(`${result.rows} rows · game ${result.game_version} · ${result.duplicate_names} duplicate names kept · ${result.catalog_path} (${result.catalog_bytes} bytes)`),
          table(["Reference file","Rows","Bytes","SHA-256"],result.sources.map(s=>[s.file,s.rows,s.bytes,el("span",{class:"mono",title:s.sha256,text:short(s.sha256)})]))):null,
        result.warnings?.length?details(`Warnings (${result.warnings.length})`,el("ul",null,result.warnings.map(w=>el("li",{text:w})))):null,
        result.diff?el("pre",{class:"code diff",tabindex:"0","aria-label":"Exact change",text:result.diff}):null,
        result.validation?.counts.error?stateBox("error",`${result.validation.counts.error} static errors in candidate.`,"Saving keeps the source editable; exporting requires errors to be fixed."):null,
        el("div",{class:"btn-row"},save,btn("Back to the form",back,"btn-ghost"))));
      box.onkeydown=e=>{if(e.key==="Escape"&&box.contains(save)){e.preventDefault();back();}};save.focus();
    }catch(e){unlock();writeFailure(e,m,d,box,null,form);}finally{d.busy=false;}
  }
  // Settings review: static cross-mod findings before and after the candidate settings (server compares both snapshots).
  // Declared order is shown as declared; nothing here says which mod wins an overlap.
  function compatImpact(m,x){
    const list=(rows,kind)=>el("ul",{class:"plain-list"},rows.map(d=>el("li",null,badge(d.severity,kind)," ",d.message,d.line&&d.file?.endsWith(".c5m")&&d.file.startsWith(`${m.project.slug}/`)?[" · ",sourceLink(m,d.line)]:d.file?el("span",{class:"faint",text:` · ${d.file}`}):null,
      el("span",{class:"faint mono",text:` ${d.code}`}))));
    const order=xs=>xs.map(i=>i.project===m.project.slug?`${i.project} (this project)`:i.project).join(" → ");
    const before=order(x.declared_order.before),after=order(x.declared_order.after);
    return panel("Compatibility impact (static)",
      p(before===after?`Declared order unchanged: ${after}.`:`Declared order: ${before} ⟶ ${after}. This is the declared order, not a verified engine load order.`,"faint"),
      x.added.length?stack(el("h4",{text:`New findings (${x.added.length})`}),list(x.added,"warn")):p("No new cross-mod or reference findings.","faint"),
      x.removed.length?stack(el("h4",{text:`No longer reported (${x.removed.length})`}),list(x.removed,"ok"),
        p("A reference that is no longer reported now matches a definition in the declared inputs or the catalog. This is static source evidence only.","faint")):null,
      x.remaining.length?details(`Unchanged findings (${x.remaining.length})`,list(x.remaining,"info")):null,p(x.note,"faint"));
  }
  // Typed evidence references: private labels with an optional SHA-256; nothing is attached or opened.
  const referenceRows=rs=>Array.isArray(rs)?rs.map((x,i)=>[`Reference ${i+1}: ${x.kind_label||x.kind}`,
    el("span",null,x.label||"",x.sha256?el("span",{class:"mono faint",text:` · SHA-256 ${x.sha256}`}):null)]):[];
  const OBS_LABELS=[["game_version","CoE5 version (as reported)"],["tester","Tester"],["class_played","Class played"],["opponents","Opponents"],["map","Map"],["turns","Turns"],["outcome","Outcome"],["reference_sha256","Reference SHA-256"]];
  const observationRows=o=>o&&typeof o==="object"&&!Array.isArray(o)?[...OBS_LABELS.filter(([k])=>o[k]!==undefined).map(([k,label])=>[label,k==="reference_sha256"?el("span",{class:"mono",text:o[k]}):String(o[k])]),["Reported by","The user (KENOGENESIS did not run or observe the game)"]]:[];
  // Server field names (error.details.field) mapped to the named controls of the current form. Only visible controls are
  // marked; an unknown or hidden field keeps the generic message. Values are never cleared.
  const FIELD_ALIASES={files:"reference-files",spr1:"art-idle",spr2:"art-attack",banner:"workshop-banner",dependencies:"dep-manual"};
  function fieldControl(form,field,message=""){
    if(!form||typeof field!=="string"||!/^[a-z0-9_.]{1,60}$/.test(field))return null;
    let mt,names;
    if((mt=field.match(/^references\.(\d+)(?:\.(kind|label|sha256))?$/)))names=[`ref-${mt[2]||"label"}-${mt[1]}`];
    else if((mt=field.match(/^assets\.(\d+)$/)))names=[`asset-path-${mt[1]}`];
    else if(/^spr[12]$/.test(field))names=/path|filename/i.test(message)?[`${FIELD_ALIASES[field]}-path`,FIELD_ALIASES[field]]:[FIELD_ALIASES[field]];
    else names=[FIELD_ALIASES[field]||field,`obs-${field}`];
    for(const n of names){const c=form.querySelector(`[name="${n}"]`);if(c&&c.getClientRects().length)return c;}
    return null;
  }
  function writeFailure(e,m,d,box,back,form) {
    const control=fieldControl(form,e.details?.field,e.message);
    box.replaceChildren(...[errorBox(e),control?p("The highlighted field shows what to change. Your entries are kept.","faint"):null].filter(Boolean));
    if(control){markInvalid(control,e.message);if(!control.disabled)reveal(control);}
    if(back)box.append(btn("Back to the form",back,"btn-ghost"));
    // A lost reply may hide a completed save, so transport failures also offer the guarded reload; nothing is resent.
    if(["stale_revision","inputs_changed","line_changed","network_error","bad_response"].includes(e.code))box.append(btn("Reload latest file (keep my form)",async()=>{
      try{await model(m.project.slug,true);toast("Latest saved revision loaded; your form is kept. Review it again before saving.");await render();}catch(x){box.append(errorBox(x));}}));
  }
  const identity=o=>JSON.stringify([o.kind,o.opener,o.name]);
  // A source position is not an identity: keep drafts from targeting a different block after reload.
  function draftRecovery(m,d,o,tab,editing) {
    if(!d.dirty||!d.identity)return null;
    const anonymous=["school","event"].includes(o.kind);
    // unplaced: the saved revision changed after this positional draft began, so even a matching name is not trusted.
    if(d.unplaced||d.identity!==identity(o)||(anonymous&&d.baseRevision!==m.revision&&d.originalText!==o.text)){
      const matches=m.objects.filter(x=>identity(x)===d.identity&&(!anonymous||x.text===d.originalText));
      return panel("Draft retained: definition moved or changed",stateBox("error","This draft cannot safely target the current source position."),
        details("Preserved field and command draft",el("pre",{class:"code",text:JSON.stringify({fields:d.fields,commands:d.ops,path:d.path,artwork:d.frames?Object.fromEntries(Object.entries(d.frames).map(([k,f])=>[k,{path:f.path,file:f.file?.filename||null}])):d.file?.filename},null,2)})),
        matches.length===1?btn("Review matching definition (keep draft)",()=>{const target=matches[0],old=d.key;d.key=old.slice(0,old.lastIndexOf(":")+1)+target.index;
          state.drafts.delete(old);state.drafts.set(d.key,d);d.unplaced=false;d.keyRev=pinOf(m);d.href=editing?route(m,tab,"edit",target.index):route(m,tab,target.index);location.hash=d.href;}):null,
        btn("Discard this draft and use current definition",()=>{state.drafts.delete(d.key);render();},"btn-ghost"));
    }
    if(d.ops&&d.baseRevision!==m.revision){const conflicts=[];
      for(const op of d.ops.filter(x=>x.line!==undefined)){
        const exact=o.statements.find(s=>s.line===op.line&&s.code===op.was),hits=exact?[exact]:o.statements.filter(s=>s.code===op.was);
        if(hits.length===1)op.line=hits[0].line;else conflicts.push(op);
      }
      if(conflicts.length)return panel("Command draft conflicts",stateBox("error","Some command rows changed outside this form."),
        el("pre",{class:"code",text:JSON.stringify(conflicts,null,2)}),btn("Discard conflicted rows (keep other form changes)",()=>{d.ops=d.ops.filter(op=>!conflicts.includes(op));d.baseRevision=m.revision;render();},"btn-ghost"));
      d.baseRevision=m.revision;
    }
    return null;
  }
  // ---------- artwork checklist: file facts from the saved revision; it never changes validation or export ----------
  const ART_GROUPS=[["missing_file","Missing or invalid files","err"],["placeholder","Inherited placeholders (copystats or copyspr)","warn"],
    ["unset","No image of their own","warn"],["overwritten","Sprite replaced by a later command","warn"],["copyspr","copyspr still present","warn"],
    ["shared","Shared files or identical bytes","warn"],["canvas","Unsupported unit canvas","warn"],["single_pose","Idle only: spr1 is shown for attacks too","info"],
    ["ready","Idle and attack files set","ok"]];
  const imageTodo=r=>r.status!=="ok";
  function artworkSummary(m){
    const A=m.readiness.artwork,U=A.units,count=k=>U[k].length;
    const todo=["placeholder","unset","overwritten","copyspr","shared","canvas"].reduce((n,k)=>n+count(k),0)+(A.banner.status==="ok"?0:1)+
      A.items.filter(imageTodo).length+A.terrain.filter(imageTodo).length;
    const kind=count("missing_file")?"err":todo?"warn":count("single_pose")?"info":"ok";
    const parts=[A.required_units?`${count("ready")} of ${A.required_units} new units have idle and attack files`:"No new units",
      count("single_pose")?`${count("single_pose")} idle only`:null,todo?`${todo} to replace or check`:null,count("missing_file")?`${count("missing_file")} missing files`:null];
    return {kind,text:parts.filter(Boolean).join(" · ")};
  }
  function artworkChecklist(m,open){
    const A=m.readiness.artwork,U=A.units;
    const target=i=>{const o=m.objects.find(x=>x.index===i);return o?objectLink(m,o):`#${i}`;};
    const group=(title,rows,kind,linkRow)=>rows.length?el("section",{class:"art-check"},el("h4",null,badge(String(rows.length),kind)," ",title),
      el("ul",{class:"art-check-list"},rows.map(r=>el("li",null,linkRow(r),r.detail?el("span",{class:"faint",text:` ${r.detail}`}):null)))):null;
    const unitGroups=ART_GROUPS.map(([k,title,kind])=>group(title,U[k],kind,r=>target(r.index)));
    const b=A.banner,imageGroup=(title,rows)=>group(title,rows,rows.some(imageTodo)?"warn":"ok",r=>[target(r.index),r.path?el("span",{class:"mono",text:` ${r.path}`}):null,r.status==="ok"?" · set":null]);
    const body=stack(
      p(`${A.required_units} new unit${A.required_units===1?"":"s"} need original idle (spr1) and attack (spr2) images by default; selected vanilla monsters need none unless you ask.`,"faint"),
      unitGroups.some(Boolean)?unitGroups:p("No new units are defined yet.","faint"),
      el("section",{class:"art-check"},el("h4",null,badge(b.status==="ok"?"set":b.status,b.status==="ok"?"ok":"warn")," Mod banner (icon, 256×64)"),
        p(b.path?`${b.path}${b.line?` · line ${b.line}`:""}${b.detail?` · ${b.detail}`:""}`:b.detail,"faint"),
        b.status==="ok"?null:p("No upload operation: add a new 256×64 file to the mod folder, then change the mod-wide icon line in a reviewed block edit.","faint")),
      imageGroup("New magic item icons (spr, 32×32 or 64×64)",A.items),imageGroup("New custom terrain images (spr)",A.terrain),
      A.items.length||A.terrain.length?p("Item and terrain images have no upload operation: add a new file, then change the spr line in a reviewed block edit.","faint"):null,
      U.selected.length?p(`Selected vanilla monsters (no new art by default): ${U.selected.map(r=>r.name).join(", ")}`,"faint"):null,
      el("ul",{class:"art-notes"},A.notes.map(n=>el("li",{text:n}))));
    const title="Artwork checklist";
    return open?el("section",{class:"panel",id:"artwork","aria-labelledby":"artwork-h"},el("h3",{id:"artwork-h",text:title}),body)
      :el("details",{class:"tech",id:"artwork"},el("summary",{text:title}),body);
  }
  // ---------- unit artwork: idle and attack are chosen, reviewed and saved together (new files + one exact source patch) ----------
  const POSES=[["spr1","idle","Idle (spr1)"],["spr2","attack","Attack (spr2)"]];
  const ZOOMS=[[1,"Native"],[2,"2×"],[3,"3×"],[4,"4×"]];
  const artName=s=>(s||"unit").toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/^_+|_+$/g,"").slice(0,40)||"unit";
  // Nearest-neighbour images scaled by whole multiples of their native width.
  function zoomImg(src,alt,native,zoom){
    const img=el("img",{src,alt,"data-zoomable":"true","data-native":native||null});
    const size=()=>{const w=Number(img.dataset.native)||img.naturalWidth;if(w)img.width=w*zoom();};
    img.addEventListener("load",()=>{if(!img.dataset.native)img.dataset.native=String(img.naturalWidth);size();});size();
    return img;
  }
  const rezoom=(root,zoom)=>{
    root.querySelectorAll("img[data-zoomable]").forEach(i=>{const w=Number(i.dataset.native)||i.naturalWidth;if(w)i.width=w*zoom;});
    root.querySelectorAll("input[data-art-zoom]").forEach(r=>{r.checked=Number(r.value)===zoom;});
  };
  function zoomControl(d,apply){
    const name=`art-zoom-${++fieldSeq}`;
    return el("fieldset",{class:"art-zoom"},el("legend",{text:"Zoom"}),ZOOMS.map(([z,label])=>{
      const r=el("input",{type:"radio",name,value:String(z),"data-art-zoom":"true"});r.checked=(d.zoom||2)===z;
      r.addEventListener("change",()=>{if(r.checked){d.zoom=z;apply();}});
      return el("label",{class:"check"},r,label);}));
  }
  const artFigure=(caption,content,note)=>el("figure",{class:"sprite-frame"},el("div",{class:"sprite-box"},content),
    el("figcaption",{class:"cap"},el("strong",{text:caption}),note?el("span",{class:"mono",text:` ${note}`}):null));
  const missingArt=text=>el("span",{class:"preview-missing",text});
  function artFacts(f){
    if(!f)return null;const g=f.margins;
    return el("dl",{class:"art-facts"},[["Canvas",`${f.width}×${f.height} ${f.format.toUpperCase()}`],["Transparency",f.transparency],
      ["Figure",`${f.figure[0]}×${f.figure[1]} px at ${f.bbox[0]},${f.bbox[1]}`],["Free pixels",`left ${g.left} · top ${g.top} · right ${g.right} · bottom ${g.bottom}`],
      f.shadow_pixels!==undefined?["Shadow pixels",String(f.shadow_pixels)]:null].filter(Boolean).flatMap(([k,v])=>[el("dt",{text:k}),el("dd",{text:v})]));
  }
  const artWarnings=ws=>ws?.length?el("ul",{class:"art-warn"},ws.map(w=>el("li",null,badge("Check","warn")," ",w))):p("No pixel warnings.","faint");
  // The reviewed result: current and new frames side by side with the server's facts and warnings.
  function artReview(m,r,d){
    const root=el("div",{class:"stack"}),zoom=()=>d.zoom||2;
    const cols=POSES.map(([cmd,pose,label])=>{
      const n=r.frames[cmd],c=r.current?.[cmd];if(!n&&!c)return null;
      const curUrl=c&&m.assets.find(a=>a.path===c.path)?.preview;
      return el("div",{class:"art-col"},el("h4",{text:label}),el("div",{class:"art-pair"},
        c?artFigure(n?"Current":"Current (kept)",curUrl?zoomImg(curUrl,`Current ${pose} frame`,c.facts?.width,zoom):missingArt(c.problem||"Unavailable"),c.path):null,
        n?artFigure("New",zoomImg(`data:image/png;base64,${n.preview}`,`New ${pose} frame`,n.facts.width,zoom),n.path):null),
        n?stack(artFacts(n.facts),artWarnings(n.facts.warnings)):c?.facts?artFacts(c.facts):null);});
    root.append(zoomControl(d,()=>rezoom(root.closest("form")||root,zoom())),el("div",{class:"art-grid"},cols),
      el("h4",{text:"Idle and attack together"}),artWarnings(r.pair_warnings));
    if(r.notes?.length)root.append(el("ul",{class:"art-notes"},r.notes.map(x=>el("li",{text:x}))));
    return root;
  }
  function artEditor(m,o) {
    const key=`${m.project.slug}:art:${o.index}`;
    const d=draft(key,{slug:m.project.slug,label:`Artwork: ${o.display}`,href:kindRoute(m,o),frames:{spr1:{path:"",file:null},spr2:{path:"",file:null}},zoom:2,
      identity:identity(o),baseRevision:m.revision,keyRev:pinOf(m),originalText:o.text});
    if(!d.dirty&&d.baseRevision!==m.revision){state.drafts.delete(key);return artEditor(m,o);}
    const recovery=draftRecovery(m,d,o,kinds[o.kind][2],false);if(recovery)return recovery;
    const sp=o.view.sprites,current={spr1:sp.idle,spr2:sp.attack},zoom=()=>d.zoom||2,box=el("div");
    const cols=POSES.map(([cmd,pose,label])=>{
      const f=d.frames[cmd],cur=current[cmd];
      const file=input(`art-${pose}`,"","file");file.accept=".png,.tga";
      const where=input(`art-${pose}-path`,f.path);where.placeholder=`units/${artName(o.display)}_${pose}.png`;
      const shown=el("div",{class:"art-new"});
      const showNew=()=>shown.replaceChildren(artFigure("New",!f.file?missingArt(f.readError?"File not read":"No new file chosen"):/\.png$/i.test(f.file.filename)?
        zoomImg(`data:image/png;base64,${f.file.base64}`,`New ${pose} frame`,null,zoom):missingArt("TGA preview appears in the review"),f.file?.filename));
      // A replacement read clears the earlier file first, so a failed or unfinished read never leaves the old file looking new.
      file.addEventListener("change",async()=>{const x=file.files[0];if(!x)return;const mine=f.readTicket=(f.readTicket||0)+1;f.reading=true;
        f.file=null;f.readError=null;box.replaceChildren();shown.replaceChildren(stateBox("loading",`Reading ${x.name}…`));
        try{if(!/\.(png|tga)$/i.test(x.name))throw new Error("Choose a .png or .tga file.");
          if(!x.size||x.size>ART_MAX)throw new Error(`Artwork files are 1 byte to ${ART_MAX/1048576} MiB (tool policy).`);
          const u=await upload(x);if(mine!==f.readTicket)return;f.file=u;}
        catch(e){if(mine!==f.readTicket)return;f.readError=`${x.name}: ${e.message||"the file could not be read"}`;file.value="";showNew();markInvalid(file,f.readError);return;}
        finally{if(mine===f.readTicket)f.reading=false;}
        if(!f.path||f.autoPath){f.path=`units/${artName(o.display)}_${pose}.${/\.tga$/i.test(x.name)?"tga":"png"}`;f.autoPath=true;where.value=f.path;}
        dirty(d);showNew();});
      where.addEventListener("input",()=>{f.path=where.value;f.autoPath=false;dirty(d);});
      showNew();
      const curView=cur?artFigure("Current",cur.url?zoomImg(cur.url,`Current ${pose} frame`,cur.width,zoom):missingArt(`${cur.status||"missing"}`),
        `${cur.path}${cur.width?` · ${cur.width}×${cur.height}`:""}`)
        :artFigure("Current",missingArt(cmd==="spr2"&&sp.idle?"Not set: spr1 is shown for attacks":sp.inherited?`Inherited via ${sp.inherited.command} (placeholder)`:"Not set"));
      return el("div",{class:"art-col"},el("h4",{text:label}),el("div",{class:"art-pair"},curView,shown),
        field(`${label} file`,file,"PNG (8-bit RGBA) or 24/32-bit TGA, up to 2 MiB, on a 32×32, 64×64 or 128×128 canvas."),field(`${label} new asset path`,where),
        btn(`Clear ${pose} file`,()=>{f.readTicket=(f.readTicket||0)+1;f.reading=false;f.file=null;f.readError=null;file.value="";file.removeAttribute("aria-invalid");file.closest(".edit-field")?.querySelector(".field-err")?.replaceChildren();showNew();box.replaceChildren();},"btn-ghost btn-small"));
    });
    const form=el("form",{class:"stack art-editor"},zoomControl(d,()=>rezoom(form,zoom())),el("div",{class:"art-grid"},cols),
      el("button",{type:"submit",class:"btn",text:"Review artwork"}),box);
    form.addEventListener("submit",e=>{e.preventDefault();
      if(POSES.some(([c])=>d.frames[c].reading)){box.replaceChildren(stateBox("error","A file is still being read.","Wait until both chosen files show a preview, then review again."));return;}
      const failed=POSES.find(([c])=>d.frames[c].readError);
      if(failed){const c=form.querySelector(`[name="art-${failed[1]}"]`);if(c)invalid(c,d.frames[failed[0]].readError);
        box.replaceChildren(stateBox("error","A chosen file could not be read.","Choose it again or clear it. Nothing was reviewed."));return;}
      const frames=POSES.filter(([c])=>d.frames[c].file).map(([c])=>({frame:c,asset_path:d.frames[c].path.trim(),content:d.frames[c].file.base64}));
      if(!frames.length){box.replaceChildren(stateBox("error","Choose an idle or attack file first."));return;}
      const noPath=POSES.find(([c])=>d.frames[c].file&&!d.frames[c].path.trim());
      if(noPath){box.replaceChildren(stateBox("error","Enter a new asset path for each chosen file."));const c=form.querySelector(`[name="art-${noPath[1]}-path"]`);if(c)invalid(c,"Enter a new relative .png or .tga path.");return;}
      const badPath=POSES.find(([c])=>d.frames[c].file&&(assetPathProblem(d.frames[c].path.trim())||!/\.(png|tga)$/i.test(d.frames[c].path.trim())));
      if(badPath){const v=d.frames[badPath[0]].path.trim(),c=form.querySelector(`[name="art-${badPath[1]}-path"]`);
        box.replaceChildren(stateBox("error","Check the new asset path."));if(c)invalid(c,assetPathProblem(v)||"Use a .png or .tga file name.");return;}
      const args={project:m.project.slug,expected_revision:m.revision,object_index:o.index,frames};
      reviewWrite(m,d,form,box,"preview_art_upload",args,"apply_art_upload",args);});
    return details("Upload artwork",p("Choose the idle and attack frames together. The review shows current and new frames side by side with pixel checks; one save writes both new files and the source change, or nothing. Existing artwork is never overwritten.","faint"),form);
  }
  function ambiguousCopy(row) {
    const command=row.kind==="monster"?"copystats":row.kind==="ritual"?"copyritual":null;
    if(!command||!(row.name_count>1))return null;
    const entry=state.meta.registry?.find(e=>e.command===command&&e.context===row.kind);
    return `"${row.name}" names ${row.name_count} ${kinds[row.kind][1].toLowerCase()} entries in the reference catalog (this is ${row.name_ordinal+1} of ${row.name_count}). ${entry?.signature||command} takes only a name${entry?.page?` (manual p.${entry.page})`:""}, and which entry the game copies is not documented, so this row cannot be used as a template. Start a new definition and set its values directly. If you accept the name-only behaviour, you can still add ${command} yourself under All commands.`;
  }
  // Typed arguments from raw inputs by signature code (s quoted, i integer, r either; ? optional). An empty optional may only trail.
  // controls (optional): the input for each argument; the failing one gets a persistent inline error and focus.
  function typedArgs(codes,raw,what,controls){
    const out=[];let ended=false;const n=Math.max(codes.length,raw.length);
    const fail=(i,text)=>{const c=controls?.[i];if(c)invalid(c,text);throw Object.assign(new Error(`${what}: ${text}`),{index:i,inline:!!c});};
    for(let i=0;i<n;i++){
      const code=codes[i]||"r?",[type,lo,hi]=code.replace("?","").split(":"),optional=code.endsWith("?"),v=String(raw[i]??"").trim();
      if(v===""){if(!optional)fail(i,`argument ${i+1} is required.`);ended=true;continue;}
      if(ended){const gap=raw.findIndex((x,k)=>k<i&&String(x??"").trim()==="");fail(gap>=0?gap:i,`fill optional argument ${(gap>=0?gap:i)+1} before argument ${i+1}; optional arguments can only be left out at the end.`);}
      if(type==="i"){if(!/^-?\d+$/.test(v))fail(i,`argument ${i+1} must be a whole number.`);
        if(lo!==undefined&&(Number(v)<Number(lo)||Number(v)>Number(hi)))fail(i,`argument ${i+1} is outside the documented range ${lo}–${hi}.`);out.push(Number(v));}
      else if(type==="r")out.push(/^-?\d+$/.test(v)?Number(v):v);else out.push(v);
    }
    return out;
  }
  // The value control inside each labelled field of a container, in argument order.
  const argInputs=box=>[...box.querySelectorAll(".edit-field")].map(f=>f.querySelector("input,select,textarea"));
  function commandCodes(kind,command){
    const row=(state.meta.forms[kind]?.rows||[]).flatMap(g=>g.commands).find(c=>c.command===command);if(row)return row.args;
    const e=state.meta.registry.find(x=>x.command===command&&(x.context===kind||x.context==="global"));
    return e?.args||(e?.manual_args||[]).map(a=>a.type+(a.optional?"?":""))||[];
  }
  // Reference checks: local definitions first, then exact catalog rows; ambiguity and version gaps are stated, never resolved by guessing.
  const refCache=new Map();
  async function catalogRows(m,kind,q,exact){
    const k=`${m.revision}|${kind}|${q}|${exact}`;if(refCache.has(k))return refCache.get(k);
    const r=await get(`${base(m)}/catalog?${new URLSearchParams({q,kind,per:exact?"100":"20"})}`);
    const out={catalog:r.catalog,rows:r.catalog.available?(exact?r.rows.filter(x=>x.name===q||String(x.id)===q):r.rows):null};
    if(refCache.size>200)refCache.clear();refCache.set(k,out);return out;
  }
  function localDefs(m,kind,value){
    return m.objects.filter(o=>o.kind===kind&&(kind==="terrain"?String(o.name)===String(value):o.name===value));
  }
  function refField(m,kind,value,atLine,label,onValue,listHost){
    const c=input("ref",value);c.setAttribute("autocomplete","off");
    const listId=`refs-${kind}-${++fieldSeq}`,list=el("datalist",{id:listId});c.setAttribute("list",listId);listHost.append(list);
    const locals=[...new Set(m.objects.filter(o=>o.kind===kind).map(o=>kind==="terrain"?String(o.name):o.name).filter(Boolean))];
    const hint=el("div",{class:"field-meta ref-hint",role:"status","aria-live":"polite"});
    const fillList=names=>list.replaceChildren(...[...new Set([...locals,...names])].slice(0,60).map(n=>el("option",{value:n})));fillList([]);
    let timer,ticket=0;
    async function check(){const v=c.value.trim(),mine=++ticket;if(!v){hint.textContent="";return;}
      const here=localDefs(m,kind,v);
      if(here.length===1){const t=here[0];hint.replaceChildren(badge(atLine!==null&&t.line>atLine?"later":"local",atLine!==null&&t.line>atLine?"warn":"ok"),
        ` Defined in this mod, line ${t.line}${atLine!==null&&t.line>atLine?"; it comes later in the file, and the manual requires prerequisites first.":"."}`);return;}
      if(here.length>1){hint.replaceChildren(badge("ambiguous","warn"),` ${here.length} definitions in this mod share this name; the first is used unless an offset is given.`);return;}
      try{const r=await catalogRows(m,kind,v,true);if(mine!==ticket)return;
        if(r.rows===null)hint.replaceChildren(badge("unverified","info")," Not defined in this mod, and no local catalog is available to check a game reference.");
        else if(r.rows.length===1){const x=r.rows[0],gap=r.catalog.game_version!==m.project.target_version;
          hint.replaceChildren(badge(gap?"version differs":"catalog",gap?"warn":"ok"),` Catalog row, game ${r.catalog.game_version}${x.source_file?`, ${x.source_file}:${x.source_line}`:""}${r.catalog.source==="snapshot"?" (from the private snapshot)":""}.`);}
        else if(r.rows.length>1)hint.replaceChildren(badge("ambiguous","warn"),` ${r.rows.length} catalog rows share this name; which one the game uses is not documented.`);
        else hint.replaceChildren(badge("unverified","info")," Not found in this mod or the catalog; it stays unverified, not necessarily missing.");
      }catch(e){if(mine===ticket)hint.textContent=`Reference check unavailable: ${e.message}`;}}
    c.addEventListener("input",()=>{onValue(c.value);clearTimeout(timer);timer=setTimeout(async()=>{check();
      if(c.value.trim().length>1)try{const r=await catalogRows(m,kind,c.value.trim(),false);if(r.rows)fillList(r.rows.map(x=>x.name));}catch(_){/* list stays local */}},250);});
    check();return field(label,c,null,hint);
  }
  function argControl(m,spec,i,value,atLine,label,onValue,listHost){
    const code=spec.args[i]||"r?",ref=spec.refs?.[i];let choices=spec.choices?.[i],help=code.endsWith("?")?"Optional; leave empty only at the end.":null;
    if(ref)return refField(m,ref,value,atLine,label,onValue,listHost);
    // power also takes 0 (latest newritpow above this unit) and -1, -2… (earlier ones); offer only schools that exist above the line.
    const rel=spec.relative&&spec.relative.arg===i?spec.relative:null;
    if(rel&&choices){
      const above=atLine==null?[]:m.objects.filter(o=>o.kind==="school"&&o.line<atLine).sort((a,b)=>a.line-b.line).reverse();
      choices=[...above.map((s,k)=>({value:String(-k),label:k?`${s.display}, ${k} before the latest above this unit`:`Latest new school above this unit: ${s.display}`})),...choices];
      help=atLine==null?`0 and negative numbers count back over new ritual schools above this unit (manual p.${rel.page}); save the unit first to choose one here.`:
        above.length?`0 is the ${rel.zero}; negative numbers pick an ${rel.negative} (manual p.${rel.page}).`:`No new ritual school above this unit, so 0 and negative numbers do not resolve here (manual p.${rel.page}).`;}
    let c;
    if(choices){c=select("arg",[["",code.endsWith("?")?"Not set":"Choose"],...choices.map(x=>[x.value,`${x.label} (${x.value})`])],value);
      if(value!==""&&!choices.some(x=>x.value===String(value))){
        const unresolved=rel&&/^\s*(0|-\d+)\s*$/.test(String(value));
        c.append(el("option",{value,text:`${value} (${unresolved?"no new ritual school that far above this unit; unresolved":"not in the manual table"})`}));c.value=value;}}
    else{c=input("arg",value,code.startsWith("i")?"number":"text");const [,lo,hi]=code.replace("?","").split(":");if(lo!==undefined){c.min=lo;c.max=hi;}}
    c.addEventListener("input",()=>onValue(c.value));c.addEventListener("change",()=>onValue(c.value));
    return field(label,c,help);
  }
  function editor(m,kind,id,donor) {
    const isNew=id==="new",o=isNew?null:kind==="global"?{index:-1,kind:"global",display:"Mod information",statements:m.global_statements}:m.objects.find(o=>o.index===Number(id)&&o.kind===kind);
    if(!isNew&&!o)return stateBox("error","Definition not found.");
    let sourceDonor=donor!==undefined?m.objects.find(x=>x.index===Number(donor)&&x.kind===kind):null;
    const key=`${m.project.slug}:edit:${kind}:${isNew?`new:${donor??""}`:id}`;
    const openers=state.meta.openers?.[kind]||[];
    const d=draft(key,{slug:m.project.slug,label:isNew?`New ${kinds[kind][1].toLowerCase()}`:`Edit ${o.display}`,href:route(m,kinds[kind][2],isNew?"new":"edit",...(isNew?(donor===undefined?[]:[donor]):[id])),
      identity:o?identity(o):null,baseRevision:m.revision,keyRev:pinOf(m),originalText:o?.text,
      fields:{},touched:{},ops:[],openerName:sourceDonor?`${sourceDonor.name} copy`:"",openerCommand:openers.find(x=>x.new&&x.command===sourceDonor?.opener)?.command||openers[0]?.command,link:{cls:"",command:"addunitrec",raw:[]}});
    if(!d.openerArgs)d.openerArgs=[d.openerName||""];
    if(!d.link)d.link={cls:"",command:"addunitrec",raw:[]};
    if(isNew&&sourceDonor&&!d.donor)d.donor=JSON.parse(JSON.stringify(sourceDonor));
    sourceDonor=d.donor||sourceDonor;
    if(!isNew&&!d.dirty&&d.baseRevision!==m.revision){state.drafts.delete(key);return editor(m,kind,id,donor);}
    if(!isNew){const recovery=draftRecovery(m,d,o,kinds[kind][2],true);if(recovery)return recovery;}
    if(isNew&&query().has("template")&&d.template!==query().get("template")){
      const template=query().get("template"),hadDraft=d.dirty;
      const load=async clean=>{const data=await get(`${base(m)}/catalog/${encodeURIComponent(template)}`),row=data.row;d.templateNotice=null;
        if(row.kind!==kind)throw new Error("That template has a different content type.");
        const ambiguous=ambiguousCopy(row);if(ambiguous){d.template=template;d.templateNotice={title:"Template not applied: duplicate name.",text:ambiguous};render();return;}
        if(clean){d.fields={};d.touched={};d.ops=[];}
        d.openerName=`${row.name} copy`;d.openerArgs=[d.openerName];d.openerCommand=openers.find(x=>x.new)?.command||d.openerCommand;d.template=template;
        if(kind==="monster"||kind==="ritual")d.ops.push({op:"add",command:kind==="monster"?"copystats":"copyritual",arguments:[row.name]});
        else for(const f of state.meta.forms[kind]?.fields||[])if(row[f.key]!==undefined){d.fields[f.key]=row[f.key];d.touched[f.key]=true;}
        dirty(d);render();};
      const failed=e=>{d.template=template;d.templateNotice={title:"Template not applied.",text:e.message||String(e)};render();};
      if(hadDraft)return panel("Choose how to use this template",p("This new-definition form already has a draft."),el("div",{class:"btn-row"},
        btn("Keep draft",()=>{d.template=template;d.templateNotice=null;render();}),btn("Replace with template",()=>load(true).catch(failed),"btn-ghost"),
        btn("Start clean",()=>{state.drafts.delete(key);location.hash=route(m,kinds[kind][2],"new");},"btn-ghost"),link("Cancel",route(m,"inspector"),"btn btn-ghost")));
      load(false).catch(failed);return stateBox("loading","Loading template…");
    }
    const from=o||sourceDonor, spec=state.meta.forms[kind]||{fields:[],rows:[]};
    const form=el("form",{class:"stack authoring"}),controls=el("fieldset",{class:"edit-group"}),result=el("div"),lists=el("div",{hidden:true});
    const atLine=isNew?null:o.line;
    // Controls whose values are converted on submit, so a failing value is marked where it was typed.
    let openerBox=null,linkBox=null;const fieldControls={},rowControls=new Map();
    const openerSpec=()=>openers.find(x=>x.command===d.openerCommand)||openers[0];
    if(isNew&&openers.length){
      const modes=openers.length>1?select("opener-mode",openers.map(x=>[x.command,`${x.new?"New":"Change existing"}: ${x.signature}`]),d.openerCommand):null;
      const argBox=el("div",{class:"edit-grid"});openerBox=argBox;
      const fillArgs=()=>{const os=openerSpec();argBox.replaceChildren();
        os.args.forEach((a,i)=>{const ct=m.game_profile?.custom_terrain,name=os.command==="selectterr"?`Terrain number (${ct?.first??500}–${ct?.last??999} for a new custom terrain)`:os.command==="selectterrgroup"?"Terrain group number":
            a.name.replace(/^./,ch=>ch.toUpperCase());
          const spec1={args:os.args.map(x=>x.code),refs:os.command==="selectmonster"&&i===0?["monster"]:[],choices:os.command==="selectclass"?[Object.entries(state.meta.tables.class||{}).map(([v,l])=>({value:v,label:l}))]:[]};
          const set=v=>{d.openerArgs[i]=v;if(i===0){d.openerName=v;dupCheck();}dirty(d);};
          const ctl=spec1.refs[i]?refField(m,"monster",d.openerArgs[i]??"",null,name,set,lists):argControl(m,spec1,i,d.openerArgs[i]??"",null,name,set,lists);
          if(a.min===0){const n=$("input",ctl);if(n){n.type="number";n.min="0";}}
          argBox.append(ctl);});
        if(!os.args.length&&kind==="event")argBox.append(p(os.summary,"faint"));
        argBox.append(dupBox);dupCheck();};
      // A new name that repeats an existing definition makes later name references ambiguous; say so while typing.
      const dupBox=el("div",{role:"status","aria-live":"polite"});
      const dupCheck=()=>{const os=openerSpec(),name=String(d.openerArgs[0]||"").trim();
        const dup=os?.new&&os.args.length?m.objects.filter(x=>x.kind===kind&&x.name===name&&name):[];
        dupBox.replaceChildren(dup.length?stateBox("warn","This name is already used.",`${dup.length} ${kinds[kind][1].toLowerCase()} definition${dup.length>1?"s":""} in this mod already use "${name}"; name references would need an offset. Choose a unique name.`):"");};
      // Keep the first argument only when both opening lines take the same kind of value (a name or a number).
      modes?.addEventListener("change",()=>{const was=openerSpec()?.args[0]?.code[0];d.openerCommand=modes.value;
        d.openerArgs=openerSpec()?.args[0]?.code[0]===was?[d.openerArgs[0]||""]:[""];dirty(d);fillArgs();});
      fillArgs();
      if(modes)controls.append(field("How the block opens",modes,"New blocks create content; select blocks change existing game content by name or number. No ID is allocated."));
      controls.append(argBox);
      if(kind==="class"){const title=input("class-name",d.fields.setclassname??sourceDonor?.display??"");title.addEventListener("input",()=>{d.fields.setclassname=title.value;d.touched.setclassname=true;dirty(d);});
        controls.append(field("Class name",title,d.openerCommand==="newclass"?"newclass must be followed by setclassname (manual p.27).":"Optional for a selected class."));}
    }
    const grid=el("div",{class:"edit-grid"});
    for(const f of spec.fields){if(isNew&&kind==="class"&&f.key==="setclassname")continue;
      const sts=from?.statements.filter(s=>s.command===f.key)||[],orig=sts.at(-1),initial=f.type==="flag"?!!orig:orig?.args[0]??"";
      if(!(f.key in d.fields))d.fields[f.key]=initial;
      let c;
      if(f.type==="flag") {c=input(f.key,"","checkbox");c.checked=!!d.fields[f.key];}
      else if(f.choices)c=select(f.key,[["","Not set"],...f.choices.map(x=>[x.value,x.label])],d.fields[f.key]);
      else if(f.type==="textarea")c=area(f.key,d.fields[f.key],3);
      else {c=input(f.key,d.fields[f.key],["int","terrain"].includes(f.type)?"number":"text");if(f.min!==undefined)c.min=f.min;if(f.max!==undefined)c.max=f.max;}
      if(d.touched[f.key])c.classList.add("changed");
      if(sts.length>1){c.disabled=true;c.title="Repeated command: use the line editor below.";}
      fieldControls[f.key]=c;
      c.addEventListener("input",()=>{d.fields[f.key]=f.type==="flag"?c.checked:c.value;d.touched[f.key]=true;c.classList.add("changed");dirty(d);});
      grid.append(field(f.label,c,`${f.help||f.signature}${f.page?` · manual p.${f.page}`:""}${orig?` · line ${orig.line}`:""}`));
    }
    controls.append(grid);
    form.append(...[el("h2",{text:d.label}),isNew&&d.templateNotice&&query().get("template")===d.template?stateBox("error",d.templateNotice.title,d.templateNotice.text):null,controls,lists].filter(Boolean));
    const lines=from?.statements.filter(s=>!s.opener&&s.command!=="endevent")||[];
    // ---- labelled rows for repeated commands (recruitment, starting forces, attacks, ritual costs and strings) ----
    const rowSpecs=new Map(spec.rows.flatMap(g=>g.commands.map(c=>[c.command,c])));
    const rowBox=el("div",{class:"stack"});
    function rowLine(rs,st,addOp){
      const pending=st?d.ops.find(x=>x.line===st.line):addOp;
      const head=el("div",{class:"row-head"},el("strong",{text:rs.label}),st?[" · ",sourceLink(m,st.line)]:[" · ",badge("new row","info")],rs.status!=="curated"?el("span",{class:"faint",text:" · arguments not checked by KENOGENESIS"}):null);
      if(pending?.op==="remove")return el("div",{class:"row-line cmd-row-removing"},head,p(st.code,"mono faint"),btn("Undo removal",()=>{d.ops=d.ops.filter(x=>x!==pending);dirty(d);fillRows();},"btn-small btn-ghost"));
      if(st&&pending?.command&&pending.command!==st.command)return el("div",{class:"row-line"},head,
        p(`Replaced with ${pending.command} in All commands (advanced). Edit it there or reset this change.`,"faint"),
        p((pending.arguments||[]).join(" · "),"mono"),btn("Reset row",()=>{d.ops=d.ops.filter(x=>x!==pending);dirty(d);fillRows();fillLines();},"btn-small btn-ghost"));
      const raw=pending?.raw?[...pending.raw]:pending?.arguments?pending.arguments.map(String):st?[...st.args]:rs.args.map(()=>"");
      const count=Math.max(rs.args.length,raw.length),fields=el("div",{class:"edit-grid"});
      const sync=()=>{if(addOp){addOp.raw=[...raw];dirty(d);return;}
        const same=raw.length===st.args.length&&raw.every((v,i)=>String(v).trim()===st.args[i]);
        d.ops=d.ops.filter(x=>x.line!==st.line);if(!same)d.ops.push({op:"replace",line:st.line,was:st.code,command:st.command,raw:[...raw],row:true});dirty(d);};
      for(let i=0;i<count;i++){const name=rs.columns[i]||`Argument ${i+1}`;
        fields.append(argControl(m,{...rs,args:rs.args.length?rs.args:raw.map(()=>"r?")},i,raw[i]??"",atLine,name,v=>{raw[i]=v;sync();},lists));}
      rowControls.set(st?st.line:addOp,argInputs(fields));
      return el("div",{class:"row-line"},head,fields,el("div",{class:"btn-row"},st?btn("Remove row",()=>{d.ops=d.ops.filter(x=>x.line!==st.line);d.ops.push({op:"remove",line:st.line,was:st.code});dirty(d);fillRows();},"btn-small btn-ghost"):
        btn("Discard new row",()=>{d.ops=d.ops.filter(x=>x!==addOp);dirty(d);fillRows();},"btn-small btn-ghost"),
        pending&&st?btn("Reset row",()=>{d.ops=d.ops.filter(x=>x!==pending);dirty(d);fillRows();},"btn-small btn-ghost"):null));
    }
    function fillRows(){rowBox.replaceChildren();
      for(const g of spec.rows){
        const existing=lines.filter(st=>g.commands.some(c=>c.command===st.command)),adds=d.ops.filter(op=>op.op==="add"&&op.row&&g.commands.some(c=>c.command===op.command));
        const fs=el("fieldset",{class:"edit-group row-group"},el("legend",{text:g.title}));
        if(!existing.length&&!adds.length)fs.append(p("None yet.","faint"));
        for(const st of existing)fs.append(rowLine(rowSpecs.get(st.command),st,null));
        for(const op of adds)fs.append(rowLine(rowSpecs.get(op.command),null,op));
        fs.append(el("div",{class:"btn-row"},g.commands.map(c=>btn(`Add ${c.label.toLowerCase()}`,()=>{d.ops.push({op:"add",row:true,command:c.command,raw:c.args.map(()=>"")});dirty(d);fillRows();fillLines();},"btn-small btn-ghost"))));
        rowBox.append(fs);
      }
      if(spec.rows.length)rowBox.append(p("Rows keep their place in the source; new rows are added at the end of this block. Unknown commands and comments are preserved.","faint"));
    }
    if(spec.rows.length){fillRows();form.append(panel("Repeated values",rowBox));}
    // ---- optional class connection for a new unit: one reviewed save inserts the unit before the class and adds its class row ----
    const classes=m.objects.filter(x=>x.kind==="class");
    if(isNew&&kind==="monster"&&classes.length){
      const linkRows=(state.meta.forms.class?.rows||[]).flatMap(g=>g.commands).filter(c=>c.refs?.[0]==="monster");
      const roleLabel={addunitrec:"Troop: recruitable unit",addcomrec:"Commander: recruitable commander",addmercrec:"Mercenary recruit",addstartunits:"Starting units",addstartcom:"Starting commander"};
      const cls=select("link-class",[["","Do not connect"],...classes.map(x=>[String(x.index),`${x.display} (line ${x.line})`])],d.link.cls);
      const role=select("link-role",linkRows.map(c=>[c.command,roleLabel[c.command]||c.label]),d.link.command),argBox=el("div",{class:"edit-grid"});linkBox=argBox;
      const fill=()=>{argBox.replaceChildren();role.disabled=!cls.value;if(!cls.value)return;const rs=linkRows.find(c=>c.command===role.value);
        rs.args.slice(1).forEach((code,j)=>argBox.append(argControl(m,{...rs,args:rs.args.slice(1),refs:[],choices:[]},j,d.link.raw[j]??"",null,rs.columns[j+1]||`Argument ${j+2}`,v=>{d.link.raw[j]=v;dirty(d);},lists)));};
      cls.addEventListener("change",()=>{d.link.cls=cls.value;dirty(d);fill();});role.addEventListener("change",()=>{d.link.command=role.value;d.link.raw=[];dirty(d);fill();});fill();
      form.append(details("Connect to a class (optional)",p("Adds one documented class row naming this unit. The new unit is inserted before that class so it is defined first, and both changes are reviewed and saved together as one source change.","faint"),
        el("div",{class:"edit-grid"},field("Class",cls),field("Role",role)),argBox,
        p("Summons are not connected here: after saving, add the unit to a summoning ritual's Strings row in its own reviewed edit. Summon string grammar needs game testing.","faint")));
    }
    const lineBox=el("div");
    function fillLines(){lineBox.replaceChildren(table(["Command","Arguments","Source",""],lines.map(st=>{
      const pending=d.ops.find(x=>x.line===st.line);return [st.label,pending?badge(pending.op==="remove"?"Removing":"Changing","warn"):st.args.join(" · "),sourceLink(m,st.line),
        el("div",{class:"btn-row"},pending?btn("Undo",()=>{d.ops=d.ops.filter(x=>x!==pending);dirty(d);fillLines();fillRows();},"btn-small btn-ghost"):
          [btn("Change",()=>commandForm(st),"btn-small btn-ghost"),btn("Remove",()=>{d.ops.push({op:"remove",line:st.line,was:st.code});dirty(d);fillLines();fillRows();},"btn-small btn-ghost")])];})));
      if(d.ops.some(x=>x.op==="add"))lineBox.append(table(["New command","Arguments",""],d.ops.filter(x=>x.op==="add").map(op=>[op.command,(op.arguments||op.raw||[]).join(" · "),btn("Undo",()=>{d.ops=d.ops.filter(x=>x!==op);dirty(d);fillLines();fillRows();},"btn-small btn-ghost")])));}
    const cmdBox=el("div");
    function commandForm(st=null){cmdBox.replaceChildren();const entries=state.meta.registry.filter(e=>e.context===kind&&e.status!=="announced"&&!/^(new|select)/.test(e.command)&&e.command!=="endevent");
      const filter=input("command-filter","","search");filter.placeholder="Filter commands by name or description";
      const chosen=select("command",entries.map(e=>[e.command,`${e.label} (${e.command})`]),st?.command||entries[0]?.command),argsBox=el("div",{class:"edit-grid"}),help=p("","faint");let raw=[];
      chosen.size=6;
      filter.addEventListener("input",()=>{const q=filter.value.toLowerCase();const keep=entries.filter(e=>`${e.command} ${e.label} ${e.summary||""}`.toLowerCase().includes(q));
        chosen.replaceChildren(...keep.map(e=>el("option",{value:e.command,text:`${e.label} (${e.command})`})));if(keep.length){chosen.value=keep[0].command;args();}});
      function args(){const entry=entries.find(e=>e.command===chosen.value);argsBox.replaceChildren();
        help.textContent=entry?`${entry.signature} · manual p.${entry.page}${entry.status!=="curated"?" · arguments not validated":""}${entry.summary?` · ${entry.summary}`:""}`:"Unknown command; use source editing to change it.";
        const codes=entry?commandCodes(kind,entry.command):[],names=entry?.arg_names||(entry?.manual_args||[]).map(a=>a.name);
        raw=codes.map((_,i)=>st?.command===chosen.value?st.args[i]??"":"");
        codes.forEach((code,i)=>argsBox.append(argControl(m,{args:codes},i,raw[i],atLine,names[i]?names[i].replace(/^./,ch=>ch.toUpperCase()):`Argument ${i+1}`,v=>{raw[i]=v;},lists)));}
      // Failures stay on screen beside the argument that caused them; nothing is added and the entered values are kept.
      const cmdErr=el("div");
      chosen.addEventListener("change",()=>{cmdErr.replaceChildren();args();});args();cmdBox.append(panel(st?`Change line ${st.line}`:"Add command",field("Find a command",filter),field("Command",chosen),help,argsBox,cmdErr,
        el("div",{class:"btn-row"},btn(st?"Keep line change":"Add to draft",()=>{cmdErr.replaceChildren();try{const entry=entries.find(e=>e.command===chosen.value);
          if(!entry){invalid(chosen,"Choose a documented command.");return;}
          const values=typedArgs(commandCodes(kind,entry.command),raw,entry.command,argInputs(argsBox));
          d.ops=d.ops.filter(x=>!st||x.line!==st.line);d.ops.push({op:st?"replace":"add",...(st?{line:st.line,was:st.code}:{}),command:chosen.value,arguments:values});dirty(d);cmdBox.replaceChildren();fillLines();fillRows();
        }catch(e){cmdErr.replaceChildren(stateBox("error","Not added to the draft yet.",e.inline?`${e.message} Fix the highlighted argument; your entries are kept.`:e.message));}}),
        btn("Cancel",()=>cmdBox.replaceChildren(),"btn-ghost"))));filter.focus();}
    fillLines();form.append(details("All commands (advanced)",p("Every authored line of this block, including commands without a structured form. Changes here and in the rows above share one draft.","faint"),lineBox,btn("Add command",()=>commandForm(),"btn-ghost"),cmdBox));
    form.append(el("div",{class:"btn-row"},el("button",{type:"submit",class:"btn",text:"Review changes"}),
      btn("Cancel and discard draft",()=>{state.drafts.delete(key);location.hash=isNew?route(m,kinds[kind][2]):kindRoute(m,o);},"btn-ghost")),result);
    form.addEventListener("submit",e=>{e.preventDefault();try{
      let changes=[];
      const activeFields=isNew&&!sourceDonor?Object.keys(d.fields):Object.keys(d.touched);
      for(const key of activeFields){const f=spec.fields.find(x=>x.key===key)||{type:"text"},value=d.fields[key];
        if(f.type==="flag"){if(value)changes.push({op:isNew?"add":"set",command:key,arguments:[]});else if(!isNew)changes.push({op:"unset",command:key});}
        else if(value===""){if(!isNew)changes.push({op:"unset",command:key});}
        else{const n=["int","rank","choice","terrain"].includes(f.type)?Number(value):value;
          if(typeof n==="number"&&!Number.isInteger(n)){if(fieldControls[key])invalid(fieldControls[key],"Enter a whole number.");throw Object.assign(new Error(`${f.label}: enter a whole number.`),{inline:!!fieldControls[key]});}
          changes.push({op:isNew?"add":"set",command:key,arguments:[n]});}}
      // Row drafts keep raw text so nothing is lost while typing; convert them here with the documented signature.
      const ops=d.ops.map(op=>{if(!op.raw)return op;const {raw,row,...rest}=op;return {...rest,arguments:typedArgs(commandCodes(kind,op.command),raw,rowSpecs.get(op.command)?.label||op.command,rowControls.get(op.line??op))};});
      if(sourceDonor&&isNew){
        const cloned=sourceDonor.statements.filter(s=>!s.opener&&s.command!=="endevent").map(st=>({op:"add",command:st.command,arguments:st.args.map((x,i)=>st.quoted[i]?x:/^-?\d+$/.test(x)?Number(x):x),line:st.line}));
        for(const op of changes){const matches=cloned.filter(c=>c.command===op.command);for(const c of matches)cloned.splice(cloned.indexOf(c),1);
          if(op.op!=="unset")cloned.push({...op,op:"add"});}
        for(const op of ops){const at=cloned.findIndex(c=>c.line===op.line);
          if(op.op==="add")cloned.push(op);else if(at>=0){if(op.op==="remove")cloned.splice(at,1);else cloned[at]={...op,op:"add"};}}
        changes=cloned.map(({line,was,...op})=>op);
      }else if(isNew){const copies=ops.filter(op=>["copystats","copyritual"].includes(op.command));changes=[...copies,...changes,...ops.filter(op=>!copies.includes(op))];}
      else changes.push(...ops);
      let opener=null,linked=null;
      if(isNew){const os=openerSpec();if(!os)throw new Error("This content type has no documented opening line.");
        const values=typedArgs(os.args.map(a=>a.code),(d.openerArgs||[]).slice(0,os.args.length),"Opening line",openerBox&&argInputs(openerBox));
        if(os.args.some((a,i)=>a.min===0&&typeof values[i]==="number"&&values[i]<0))throw new Error("Opening line: the offset cannot be negative.");
        opener={command:os.command,arguments:values};
        if(kind==="monster"&&d.link.cls){const name=values[0];
          if(os.command==="newmonster"&&m.objects.some(x=>x.kind==="monster"&&x.name===name))throw new Error("Another monster already uses this name, so a class row could not tell them apart. Choose a unique name or connect it later.");
          const rs=(state.meta.forms.class?.rows||[]).flatMap(g=>g.commands).find(c=>c.command===d.link.command);
          linked={object_index:Number(d.link.cls),changes:[{op:"add",command:rs.command,arguments:[name,...typedArgs(rs.args.slice(1),d.link.raw,rs.label,linkBox&&argInputs(linkBox))]}]};}}
      const args={project:m.project.slug,expected_revision:m.revision,object_index:o?.index??null,changes,mode:isNew?"new":"edit",opener,...(linked?{linked}:{})};
      reviewWrite(m,d,form,result,"preview_block_edit",args,"apply_block_edit",args);
    }catch(e){result.replaceChildren(...[errorBox(e),e.inline?p("The highlighted field shows what to fix. Your draft is kept.","faint"):null].filter(Boolean));}});
    return el("div",{class:"stack"},sectionModes(m,kind,o,isNew?"new":"edit"),form);
  }
  async function sourceView(m,line,editing=false) {
    const source=await getText(`${base(m)}/source`);
    if(editing&&source.includes("\r\n")&&/(?<!\r)\n/.test(source))return stateBox("error","This source mixes newline conventions.","Use individual command rows or a targeted CLI patch to preserve every other line ending.");
    if(!editing){const requested=Number(line),target=Number.isSafeInteger(requested)&&requested>0?requested:null,lines=source.split(/\r?\n/);
      const code=el("pre",{class:"code source-code",tabindex:"0","aria-label":`${m.provenance.file} source (scrolls)`});lines.forEach((text,i)=>{
      // The linked line is focusable and named, so render() can focus it without scrolling the page (focusSourceLine).
      const row=el("span",{id:`L${i+1}`,class:`ln${target===i+1?" hl":""}`,"data-n":i+1,...(target===i+1?{tabindex:"-1",role:"group",
        "aria-label":`Linked line ${i+1} of ${m.provenance.file}: ${text.trim().slice(0,160)||"blank line"}`}:{})});
      const re=/"[^"\r\n]*"|#[^\r\n]*|^\s*[+-]?[a-z][a-z0-9_]*|-?\d+/g;let at=0,hit;
      while((hit=re.exec(text))){row.append(text.slice(at,hit.index),el("span",{class:hit[0].startsWith('"')?"c-str":hit[0].startsWith("#")?"c-comment":/^-?\d+$/.test(hit[0])?"c-num":"c-cmd",text:hit[0]}));at=re.lastIndex;}
      row.append(text.slice(at));code.append(row);});
      return stack(el("div",{class:"btn-row"},link("Edit source",route(m,"author","source"),"btn btn-ghost"),link("Download .c5m",`${base(m)}/source?download=1`,"btn btn-ghost")),
        line!==undefined&&!target?stateBox("warn","The line reference is not a positive whole number.","The saved source is shown without a highlighted line."):
        target&&!$(`#L${target}`,code)?stateBox("warn",`Line ${target} is not in the saved source.`,`${m.provenance.file} has ${lines.length-(lines.at(-1)===""?1:0)} lines; the link may predate a later save.`):null,code);}
    const key=`${m.project.slug}:source`;
    // A clean draft is only a cache of the saved file: never let it outlive a newer source.
    if(state.drafts.get(key)&&!state.drafts.get(key).dirty&&state.drafts.get(key).original!==source)state.drafts.delete(key);
    const d=draft(key,{slug:m.project.slug,label:"Source edit",href:route(m,"author","source"),text:source,original:source,baseRevision:m.revision});
    const stale=d.original!==source;
    const text=area("source",d.text,28);text.classList.add("code");text.setAttribute("aria-label",`${m.provenance.file} source`);text.addEventListener("input",()=>{d.text=text.value;dirty(d);});
    const discard=()=>btn("Discard my source draft and load latest",()=>{state.drafts.delete(key);syncDrafts();render();},"btn-ghost");
    const form=el("form",{class:"stack"}),box=el("div");
    form.append(el("h2",{text:"Edit source"}),
      ...(stale?[stateBox("warn","The saved source changed after this draft began.","Your text is kept. Review compares it with the source it started from and applies only your edited lines, if they still appear exactly once in the latest file."),
        el("div",{class:"btn-row"},discard())]:[]),
      text,el("button",{class:"btn",type:"submit",text:"Review source change"}),box);
    form.addEventListener("submit",e=>{e.preventDefault();const entered=d.text.replace(/\r\n?/g,"\n").replace(/\n/g,m.provenance.newline==="CRLF"?"\r\n":"\n");
      // Diff against the draft's own base, never the latest file: a stale full text must not revert newer edits.
      const old=d.original;
      if(old===entered){box.replaceChildren(stateBox("ok","Nothing to save."));return;}
      let start=0,endOld=old.length,endNew=entered.length;
      while(start<endOld&&start<endNew&&old[start]===entered[start])start++;
      while(endOld>start&&endNew>start&&old[endOld-1]===entered[endNew-1]){endOld--;endNew--;}
      // Whole line context makes the changed span unique while preserving every outside byte.
      start=old.lastIndexOf("\n",Math.max(0,start-1))+1;
      // Appending after a final newline still needs a nonempty saved line as its patch anchor.
      if(start===old.length&&start>0)start=start>1?old.lastIndexOf("\n",start-2)+1:0;
      let stop=old.indexOf("\n",endOld);if(stop<0)stop=old.length;else stop++;
      const tail=stop-endOld;endNew+=tail;endOld=stop;
      const span=old.slice(start,endOld);
      if(stale){const at=span?source.indexOf(span):-1;
        if(at<0||source.indexOf(span,at+1)>=0){box.replaceChildren(stateBox("error","Your edited lines changed in the latest source.",
          at<0?"The lines this draft replaces are no longer in the saved file, so it cannot be applied without guessing.":"The lines this draft replaces now appear more than once, so the target is ambiguous."),
          details("Lines this draft expected to replace",el("pre",{class:"code",text:span||"(empty)"})),
          details("Your replacement lines",el("pre",{class:"code",text:entered.slice(start,endNew)||"(empty)"})),
          p("Copy what you need from the editor, then discard the draft to start from the latest source.","faint"),el("div",{class:"btn-row"},discard()));
          return;}}
      const args={project:m.project.slug,expected_revision:m.revision,old:span,new:entered.slice(start,endNew)};
      reviewWrite(m,d,form,box,"preview_patch",args,"apply_patch",args);});return form;
  }
  // The definition that names an asset: its own sheet, or the mod information editor for mod-wide lines such as icon.
  function assetUser(m,u){
    if(u.kind==="global"||u.object==null)return link("Mod information",route(m,"mod-info","edit","-1"));
    const o=m.objects.find(x=>x.index===u.object);return o?objectLink(m,o):el("span",{text:u.name||"Unknown definition"});
  }
  // Copy a full SHA-256 with a persistent outcome; a refused clipboard shows the full hash selected for manual copying.
  function hashCopy(a){
    const outcome=el("div",{role:"status","aria-live":"polite"}),manual=el("div");
    const b=btn("Copy hash",async()=>{manual.replaceChildren();
      if(await copyText(a.sha256)){outcome.replaceChildren(stateBox("ok",`SHA-256 copied at ${new Date().toLocaleTimeString()}.`));return;}
      const box=el("input",{class:"input mono",readonly:true,spellcheck:"false",value:a.sha256,"aria-label":`SHA-256 of ${a.path} to copy manually`});
      outcome.replaceChildren(stateBox("error","Copy failed: the browser did not allow clipboard access.","The full hash is selected below; copy it with Ctrl+C (or ⌘C)."));
      manual.replaceChildren(box);box.focus();box.select();},"btn-small btn-ghost");
    b.setAttribute("aria-label",`Copy SHA-256 of ${a.path}`);
    return {button:b,outcome,manual};
  }
  function assetsView(m) {
    const skipped=m.assets_skipped||[],listed=new Set(m.assets.map(a=>a.path));
    const included=m.assets.filter(a=>a.used_by?.length||a.declared).length,problems=m.assets.filter(a=>a.status!=="ok").length;
    const reasons=[...skipped.reduce((n,s)=>n.set(s.reason,(n.get(s.reason)||0)+1),new Map())];
    // Coverage of the folder listing: skipped paths are named with their reason, never counted as absent from export.
    const coverage=skipped.length?stack(stateBox("warn",`Folder scan skipped ${skipped.length} path${skipped.length===1?"":"s"}; the inventory may be incomplete`,
        reasons.map(([r,n])=>`${n} × ${r}`).join("; ")+"."),
      p("Referenced and declared paths are listed and checked separately, even when the folder scan skipped them. A skipped path may therefore still appear below. Unreferenced files are not part of the export. Linked files and folders are never followed.","faint"),
      details(`Skipped paths (${skipped.length})`,el("ul",{class:"plain-list"},skipped.map(s=>el("li",null,el("span",{class:"mono",text:s.path}),` — ${s.reason}`,
        listed.has(s.path)?el("span",{class:"faint",text:" (listed above as referenced or declared)"}):null))))):
      p("No skipped file paths were reported by the folder scan. Linked folders are never followed.","faint");
    const card=a=>{const copy=a.sha256?hashCopy(a):null;
      return el("article",{class:`asset-card${a.status!=="ok"?" missing":""}`},
      a.preview?el("div",{class:"sprite-box"},el("img",{src:a.preview,alt:a.path,loading:"lazy"})):null,
      el("h3",{text:a.path}),p(`${a.format||"file"}${a.width?` · ${a.width}×${a.height}${a.depth!=null?` · ${a.depth} bit`:""}`:""} · ${a.bytes??0} bytes`,"faint"),
      a.status!=="ok"?badge(a.status,"err"):null,p(a.problem||a.checks||"","faint"),
      a.used_by?.length?table(["Used by","Command","Source"],a.used_by.map(u=>[assetUser(m,u),el("span",{class:"mono",text:u.command}),sourceLink(m,u.line)])):null,
      a.declared?p("Declared export file (project settings).","faint"):a.used_by?.length?null:p("Unreferenced file: not included in the export.","faint"),
      a.format==="coem"?p("Map payload: packaged unchanged. Geometry, contents and dependencies are not interpreted.","faint"):null,
      a.sha256?el("p",{class:"hash"},"SHA-256 ",el("span",{title:a.sha256,text:short(a.sha256)})):null,
      el("div",{class:"btn-row"},a.url?el("a",{href:`${a.url}?download=1`,class:"btn btn-small btn-ghost","aria-label":`Download ${a.path}`,text:"Download"}):null,
        copy?.button,
        a.format==="coem"&&a.url?btn("Show file header",e=>peekFile(a,e.currentTarget.closest(".asset-card").querySelector(".peek")),"btn btn-small btn-ghost"):null),
      copy?.outcome,copy?.manual,
      a.format==="coem"?el("div",{class:"peek","aria-live":"polite"}):null);};
    return stack(el("h2",{text:"Assets"}),
      p(`${m.assets.length} file${m.assets.length===1?"":"s"} listed · ${included} referenced or declared for export · ${m.assets.length-included} unreferenced · ${problems} missing, unsafe or invalid`,"faint"),
      coverage,
      m.assets.length?el("div",{class:"gallery"},m.assets.map(card)):stateBox("empty","No asset files.",
        skipped.length?"No asset files could be listed. Review the skipped paths above.":
          "No referenced, declared or readable asset files were found. Add files to the mod folder, or use a unit's Upload artwork."));
  }
  function compatReport(m,r){
    const cr=r.change_review,status={appended:["appended","ok"],unchanged:["unchanged","ok"],reordered_or_removed:["reordered or removed","err"]};
    return stack(
      panel("Declared load order",p(r.load_order_note,"faint"),table(["Order","Project","modprio"],r.declared_inputs.map((x,i)=>[String(i+1),x.project===m.project.slug?`${x.project} (this project)`:x.project,x.modprio])),
        m.project.dependencies.length?link("Change the declared order in Project settings",route(m,"overview","settings"),"btn btn-small btn-ghost"):p("No dependencies declared.","faint")),
      panel("Cross-mod and reference findings",r.diagnostics.length?diagnostics(m,r.diagnostics):stateBox("ok","No overlapping targets, ambiguous names or unresolved references in the declared inputs.")),
      cr?panel("Definition order since the chosen export",
        cr.definition_order_risks.length?stateBox("error","Earlier definitions moved or were removed",`Affected: ${cr.definition_order_risks.join(", ")}. Saves made with the earlier release may depend on definition order; review before releasing. This is a static warning, not proof either way.`):
          stateBox("ok","Earlier definitions keep their order","New definitions were only appended. This does not prove save compatibility."),
        table(["Kind","Earlier","Now","Status","First difference","Removed","Added"],cr.kinds.map(k=>[kinds[k.kind]?.[1]||k.kind,k.baseline_count,k.current_count,badge(...(status[k.status]||[k.status,"info"])),
          k.first_difference===null?"—":`position ${k.first_difference+1}`,k.removed.join(", ")||"—",k.added.join(", ")||"—"])),
        p(`Compared with ${cr.baseline} (revision ${short(cr.baseline_revision)}, manifest ${short(cr.baseline_sha256)}). ${cr.note}`,"faint")):null,
      el("ul",{class:"art-notes"},r.limitations.map(n=>el("li",{text:n}))));
  }
  async function validationView(m) {
    const compat=el("div",{"aria-live":"polite"}),key=`${m.project.slug}:baseline`;let exports=[],historyError=null;
    // A failed read of the export history is reported as unavailable, never as "no earlier exports".
    try{exports=(await get(`${base(m)}/exports`)).exports.filter(x=>!x.error);}catch(e){historyError=e;}
    const choose=select("baseline",[["","No earlier export (declared inputs only)"],...exports.map(x=>[x.manifest_path,`${new Date(x.created_ns/1e6).toLocaleString()} · ${short(x.revision)}${x.revision===m.revision?" · this revision":""}`])],state.filters.get(key)||"");
    choose.addEventListener("change",()=>state.filters.set(key,choose.value));
    const b=btn("Check compatibility",async()=>{b.disabled=true;compat.replaceChildren(stateBox("loading","Checking…"));
      try{compat.replaceChildren(compatReport(m,await api("compatibility",{project:m.project.slug,baseline:choose.value||null})));}catch(e){compat.replaceChildren(errorBox(e));}finally{b.disabled=false;}});
    if(historyError){choose.replaceChildren(el("option",{value:"",text:"Export history unavailable (declared inputs only)"}));choose.value="";}
    const unavailable=historyError?stack(stateBox("warn","Earlier exports could not be read.",`${historyError.message||historyError} You can still check the declared inputs; retry to compare with an earlier export.`),
      btn("Retry reading export history",()=>render(),"btn-small")):null;
    return stack(diagnostics(m),panel("Compatibility",p("Checks declared dependencies, shared targets and, against an earlier export, whether existing definitions kept their order.","faint"),
      unavailable,field("Earlier export to compare",choose,historyError?"The export history is unavailable right now.":exports.length?"Choose the release players may have saves from.":"No earlier exports yet; export once to create a baseline."),b,compat));
  }
  // The latest export result of each project, kept for this browser tab (sessionStorage), never in the export payload.
  const exportKey=slug=>`kenogenesis:export:${slug}`;
  function exportOutcome(slug){try{return JSON.parse(storeGet("sessionStorage",exportKey(slug))||"null");}catch(_){return null;}}
  function exportResult(m,x){
    const listed=m.exports.find(e=>e.export_id===x.export_id),current=x.revision===m.revision;
    const dismiss=btn("Dismiss",()=>{storeSet("sessionStorage",exportKey(m.project.slug),null);render();},"btn-ghost btn-small");dismiss.setAttribute("aria-label","Dismiss export result");
    // The hash list stays copyable: the outcome is shown persistently, and a refused clipboard reveals the text to copy by hand.
    const hashText=[`KENOGENESIS export ${x.export_id} · project ${m.project.slug} · revision ${x.revision}`,
      `archive SHA-256  ${x.archive_sha256||"none (folder export)"}`,`manifest  ${x.manifest_path||x.manifest}`,
      ...(x.files||[]).map(f=>`${f.sha256}  ${f.bytes}  ${f.path}`)].join("\n");
    const copyOutcome=el("div",{role:"status","aria-live":"polite"}),copyManual=el("div");
    const copyHashes=btn("Copy file and archive hashes",async()=>{copyManual.replaceChildren();
      if(await copyText(hashText)){copyOutcome.replaceChildren(stateBox("ok",`Hashes copied at ${new Date().toLocaleTimeString()}.`));return;}
      const box=el("textarea",{class:"input code",rows:String(Math.min(12,4+(x.files||[]).length)),readonly:true,spellcheck:"false","aria-label":"Export hashes to copy manually",text:hashText});
      copyOutcome.replaceChildren(stateBox("error","Copy failed: the browser did not allow clipboard access.","The hashes are selected below; copy them with Ctrl+C (or ⌘C)."));
      copyManual.replaceChildren(box);box.focus();box.select();},"btn-small btn-ghost");
    return el("section",{class:"panel",id:"export-result","aria-labelledby":"export-result-h"},
      el("div",{class:"receipt-head"},el("h3",{id:"export-result-h",tabindex:"-1"},badge("exported","ok")," Export result"),el("span",{class:"faint",text:new Date(x.time).toLocaleString()}),dismiss),
      current?null:stateBox("warn","The project changed after this export.","This export is of an older revision. You can export the saved revision again."),
      listed?null:stateBox("warn","This export is no longer listed.","Its files may have been moved or removed outside the workshop."),
      el("dl",{class:"kv receipt-facts"},el("dt",{text:"Export"}),el("dd",{class:"mono",text:x.export_id}),el("dt",{text:"Format"}),el("dd",{text:x.format==="zip"?"ZIP archive":"Folder"}),
        el("dt",{text:"Revision"}),el("dd",{class:"mono",text:`${x.revision}${current?" (saved revision)":""}`}),
        el("dt",{text:"Archive SHA-256"}),el("dd",{class:"mono",text:x.archive_sha256||"Not applicable: folder export"}),
        el("dt",{text:"Manifest"}),el("dd",{class:"mono",text:x.manifest_path||x.manifest}),
        el("dt",{text:"Static checks"}),el("dd",{text:`${x.counts.error} errors · ${x.counts.warning} warnings · ${x.counts.unverified} unverified`})),
      table(["File in export","Bytes","SHA-256"],(x.files||[]).map(f=>[el("span",{class:"mono",text:f.path}),f.bytes,el("span",{class:"mono",title:f.sha256,text:short(f.sha256)})])),
      el("div",{class:"btn-row"},copyHashes),copyOutcome,copyManual,
      x.warnings?.length?details(`Warnings (${x.warnings.length})`,el("ul",null,x.warnings.map(w=>el("li",{text:w})))):null,
      x.dependencies?.length?p(`Requires ${x.dependencies.join(", ")}; dependencies are not bundled.`,"faint"):null,
      listed?el("div",{class:"btn-row"},x.format==="zip"?link("Download ZIP",`${base(m)}/exports/${x.export_id}/archive`,"btn btn-small"):p(listed.path,"mono"),
        link("Manifest JSON",`${base(m)}/exports/${x.export_id}/manifest?download=1`,"btn btn-small btn-ghost")):null,
      p("Static checks only. Exporting does not install, publish or prove that the mod works in the game.","faint"));
  }
  function exportFailure(e,m,d,box){
    if(e.code==="validation_failed"){const n=e.details?.counts?.error;box.replaceChildren(stack(stateBox("error","Export blocked by static errors.",
      `${n?`${n} static error${n===1?"":"s"} must be fixed first. `:""}Nothing was exported.`),link("Open the validation report",route(m,"validation"),"btn btn-small")));return;}
    if(e.code==="stale_revision"){box.replaceChildren(stateBox("error","The saved project changed since this page loaded.","Nothing was exported. Reload the latest saved revision, review it, then export again."),
      btn("Reload latest saved revision",async()=>{try{await model(m.project.slug,true);await render();}catch(x){box.append(errorBox(x));}},"btn-small"));return;}
    writeFailure(e,m,d,box);
  }
  function exportView(m) {
    const d=draft(`${m.project.slug}:export-ui`,{slug:m.project.slug,label:"Export",href:route(m,"export")});
    const format=select("format",[["zip","ZIP archive"],["folder","Folder"]],"zip"),result=el("div",{"aria-live":"polite"});format.setAttribute("aria-label","Export format");
    const exportBtn=btn("Export saved revision",async()=>{exportBtn.disabled=true;result.replaceChildren(stateBox("loading","Exporting the saved revision…"));
      try{const r=await post("export_mod",{project:m.project.slug,expected_revision:m.revision,format:format.value});
        storeSet("sessionStorage",exportKey(m.project.slug),JSON.stringify({...r,time:Date.now()}));state.focusExport=true;
        state.models.delete(m.project.slug);toast("Saved revision exported.");await render();}catch(e){exportFailure(e,m,d,result);}finally{exportBtn.disabled=!m.validation.static_ok;}});
    exportBtn.disabled=!m.validation.static_ok;
    // Re-validate only reads the saved project: a failure keeps the cached model and drafts, shows its reason beside the
    // action with Retry, and leaves the button usable. Export itself stays a separate, explicitly triggered write.
    const revalidate=btn("Re-validate",async()=>{if(revalidate.disabled)return;revalidate.disabled=true;
      result.replaceChildren(stateBox("loading","Re-validating the saved project…"));
      try{await model(m.project.slug,true);result.replaceChildren();await render();}
      catch(e){result.replaceChildren(errorBox(e,()=>{revalidate.focus();revalidate.click();},"the latest validation","export-revalidate-retry"));}
      finally{revalidate.disabled=false;}},"btn-ghost");
    revalidate.id="export-revalidate";
    const outcome=exportOutcome(m.project.slug);
    if(outcome&&state.focusExport){state.focusExport=false;requestAnimationFrame(()=>$("#export-result-h")?.focus());}
    const exports=m.exports.map(x=>[new Date(x.created_ns/1e6).toLocaleString(),short(x.revision),x.error||x.format,
      el("div",{class:"btn-row"},x.format==="zip"?link("Download ZIP",`${base(m)}/exports/${x.export_id}/archive`,"btn btn-small"):p(x.path,"mono"),
        link("Manifest JSON",`${base(m)}/exports/${x.export_id}/manifest?download=1`,"btn btn-small btn-ghost"))]);
    const drafts=activeDrafts(m.project.slug);
    const L=m.latest_export;
    return stack(outcome?.export_id&&outcome.counts?exportResult(m,outcome):null,panel("Export saved project",p(`Saved revision: ${short(m.revision)}`,"mono"),
      !m.validation.static_ok?stack(stateBox("error","Export blocked by static errors.","Fix the validation report first."),link("Open the validation report",route(m,"validation"),"btn btn-small btn-ghost")):
        L&&!L.error&&L.revision!==m.revision?stateBox("warn","The latest export is outdated.","It was made from an older revision. Export the saved revision to bring it up to date."):null,
      drafts.length?panel("Unsaved drafts are not included",el("ul",null,drafts.map(x=>el("li",null,link(x.label,x.href)," ",btn("Discard draft",()=>{state.drafts.delete(x.key);render();},"btn-small btn-ghost"))))):null,
      el("div",{class:"btn-row"},format,exportBtn,revalidate),result),
      exportHandoff(m),
      workshopPanel(m),
      panel("Exports",exports.length?table(["Created","Revision","Format","Files"],exports):stateBox("empty","No exports yet.")));
  }
  // GitHub-style heading slugs, so links such as [x](#keyboard-and-narrow-screens) and FILE.md#anchor land on the heading.
  const slugify=t=>t.toLowerCase().replace(/[`*_]/g,"").replace(/[^\p{L}\p{N}\s-]/gu,"").trim().replace(/\s/g,"-");
  // linkTo(name, anchor) builds the route of another .md guide; project notes link to sibling notes, global guides to guides.
  const guideLink=(name,anchor)=>path("docs",name)+(anchor?`?h=${encodeURIComponent(anchor)}`:"");
  // Block structure follows the reference renderer: numbered items stay an ordered list, indented lines continue their list
  // item, and wrapped lines join one paragraph. Every string still becomes text nodes through inline(); no HTML is parsed.
  function markdown(text,doc,linkTo=guideLink) {
    const root=el("div",{class:"md prose"}),lines=text.split(/\r?\n/),used=new Map();
    const cells=line=>line.trim().replace(/^\||\|$/g,"").split("|").map(x=>x.trim());
    const isRow=l=>/^\s*\|.*\|\s*$/.test(l),isItem=l=>/^\s*(?:[-*]|\d+\.)\s+/.test(l),isHead=l=>/^#{1,6}\s+/.test(l);
    let i=0;
    while(i<lines.length){const line=lines[i];
      if(line.startsWith("```")){const code=[];i++;while(i<lines.length&&!lines[i].startsWith("```"))code.push(lines[i++]);i++;
        root.append(el("pre",{class:"code",text:code.join("\n")}));continue;}
      if(!line.trim()){i++;continue;}
      const h=line.match(/^(#{1,6})\s+(.*)$/);if(h){let id=slugify(h[2]);const n=used.get(id)||0;used.set(id,n+1);if(n)id=`${id}-${n}`;
        root.append(el(`h${Math.min(4,h[1].length)}`,{id:`doc-${id}`,tabindex:"-1"},inline(h[2],doc,linkTo)));i++;continue;}
      if(isRow(line)){const rows=[];while(i<lines.length&&isRow(lines[i]))rows.push(lines[i++]);
        // Without a header separator the rows are ordinary text, one paragraph each.
        if(!(rows.length>1&&/^\s*\|?[\s:|-]+\|?\s*$/.test(rows[1])&&rows[1].includes("-"))){rows.forEach(r=>root.append(el("p",null,inline(r,doc,linkTo))));continue;}
        const [head,,...body]=rows;
        root.append(el("div",{class:"table-wrap"},el("table",{class:"data"},el("thead",null,el("tr",null,cells(head).map(x=>el("th",{scope:"col"},inline(x,doc,linkTo))))),
          el("tbody",null,body.map(r=>el("tr",null,cells(r).map(x=>el("td",null,inline(x,doc,linkTo)))))))));continue;}
      if(isItem(line)){const first=line.match(/^\s*(\d+)\./),list=el(first?"ol":"ul",{start:first&&first[1]!=="1"?first[1]:null});
        while(i<lines.length&&isItem(lines[i])&&/^\s*\d+\./.test(lines[i])===!!first){let item=lines[i++].replace(/^\s*(?:[-*]|\d+\.)\s+/,"");
          while(i<lines.length&&/^\s{2,}\S/.test(lines[i])&&!isItem(lines[i]))item+=` ${lines[i++].trim()}`;
          list.append(el("li",null,inline(item,doc,linkTo)));}
        root.append(list);continue;}
      const para=[];
      while(i<lines.length&&lines[i].trim()&&!lines[i].startsWith("```")&&!isHead(lines[i])&&!isItem(lines[i])&&!isRow(lines[i]))para.push(lines[i++].trim());
      root.append(el("p",null,inline(para.join(" "),doc,linkTo)));
    }
    return root;
  }
  // Internal anchors become ?h= routes: the hash router owns location.hash, so a bare #anchor would leave the page.
  function inline(text,doc,linkTo=guideLink) {
    const out=[];const re=/\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*/g;let start=0,hit;
    while((hit=re.exec(text))){out.push(text.slice(start,hit.index));if(hit[3])out.push(el("code",{text:hit[3]}));else if(hit[4])out.push(el("strong",{text:hit[4]}));
      else {const target=hit[2];
        if(/^https?:/.test(target))out.push(link(hit[1],target));
        else{const [file,anchor]=target.split("#"),name=file?file.split("/").at(-1):doc;
          out.push(name&&/\.md$/i.test(name)?link(hit[1],linkTo(name,anchor)):hit[1]);}}
      start=re.lastIndex;}out.push(text.slice(start));return out;
  }
  // Global guides are the tool's own docs. Inside a project, private notes (top-level .md files of <project>/docs/, read
  // through a bounded GET route) are listed separately; both render as data through the same textContent-only renderer.
  async function docsView(name,m=null,projectNote=false) {
    const withAnchor=(href,anchor)=>href+(anchor?`?h=${encodeURIComponent(anchor)}`:"");
    const guideHref=n=>m?route(m,"docs",n):path("docs",n),noteHref=n=>route(m,"docs","project",n);
    const nav=el("nav",{class:"btn-row","aria-label":"KENOGENESIS guides"},state.meta.docs.map(d=>link(d.name.replace(/\.md$/,""),guideHref(d.name),"btn btn-ghost btn-small")));
    nav.querySelectorAll("a").forEach(a=>{if(!projectNote&&name&&a.getAttribute("href")===guideHref(name))a.setAttribute("aria-current","page");});
    let notes=null;
    if(m){let listing;
      try{listing=await get(`${base(m)}/docs`);}catch(e){listing={error:e};}
      const where=`${state.meta.workspace}/${m.project.slug}/docs/`;
      notes=stack(el("h2",{text:"Project notes (private)"}),listing.error?errorBox(listing.error,()=>render(),"the list of private project notes"):listing.docs.length?
        el("nav",{class:"btn-row","aria-label":"Private project notes"},listing.docs.map(d=>{const a=link(d.name.replace(/\.md$/,""),noteHref(d.name),"btn btn-ghost btn-small");
          if(projectNote&&d.name===name)a.setAttribute("aria-current","page");return a;})):
        p(`No private notes. Markdown files placed directly in ${where} appear here.`,"faint"),
        listing.skipped?.length?details(`Not shown (${listing.skipped.length})`,el("ul",null,listing.skipped.map(x=>el("li",{text:`${x.name}: ${x.reason}`})))):null,
        p("Read-only. Only .md files directly in the project's docs/ folder, up to 256 KiB each; names suggesting secrets or backups, links and subfolders are skipped. Notes are never edited here or exported.","faint"));}
    const head=stack(m?el("h2",{text:"Guides"}):null,nav,notes);
    if(!name)return stack(head,p(m?"Choose a guide or a project note.":"Choose a guide."),link("Official CoE5 modding manual",state.meta.manual.url));
    let body,info=null;
    if(projectNote){
      try{const r=await get(`${base(m)}/docs/${encodeURIComponent(name)}`);
        body=markdown(r.text,name,(n,a)=>withAnchor(noteHref(n),a));
        info=el("p",{class:"faint"},badge("private note","warn"),` ${r.name} · ${r.bytes} bytes · SHA-256 ${short(r.sha256)} · read-only, never exported`);}
      catch(e){return stack(head,errorBox(e,()=>render(),`the note ${name}`,"section-retry"),link("Back to project notes",route(m,"docs"),"btn btn-small btn-ghost"));}
    }else{
      // A missing or unreadable guide keeps the guide navigation above, with the server's typed reason and Retry.
      let text;try{text=await getText(`/api/docs/${encodeURIComponent(name)}`);}
      catch(e){return stack(head,errorBox(e,()=>render(),`the guide ${name}`,"section-retry"),p(m?"Choose another guide above, or another section of this project.":"Choose another guide above.","faint"));}
      body=markdown(text,name,m?(n,a)=>withAnchor(guideHref(n),a):guideLink);
    }
    const anchor=query().get("h");
    if(anchor)requestAnimationFrame(()=>{const target=document.getElementById(`doc-${slugify(anchor)}`)||document.getElementById(`doc-${anchor}`);if(target){target.scrollIntoView({block:"start"});target.focus({preventScroll:true});}});
    return stack(head,info,body);
  }
  // ---------- vanilla catalog inspector: list and detail side by side (stacked when narrow); results refresh in place ----------
  const CAT_OPS=[["eq","equals"],["ne","does not equal"],["contains","contains"],["gt","greater than"],["ge","at least"],["lt","less than"],["le","at most"],["exists","is present"],["missing","is missing"]];
  const CAT_DEFAULTS={q:"",kind:"",sort:"name",order:"asc",page:"1",per:"40",conditions:"[]"};
  const KENO_ENTRY=Object.freeze({keno:true});
  // Address conditions are checked before any request: a malformed or out-of-range filter is rejected, never sent or applied.
  function parseConditions(raw){
    let v;try{v=JSON.parse(raw||"[]");}catch(_){return null;}
    const ops=new Set(CAT_OPS.map(x=>x[0]));
    return Array.isArray(v)&&v.length<=8&&v.every(c=>c&&typeof c==="object"&&!Array.isArray(c)&&typeof c.field==="string"&&c.field&&ops.has(c.op)&&
      ["string","number","undefined"].includes(typeof c.value)&&String(c.value??"").length<=120)?v:null;
  }
  async function catalogDetail(m,index,backToList){
    {const r=await get(`${base(m)}/catalog/${index}`),row=r.row,c=r.catalog;
      const kindKey=String(row.kind).replace(/_selection$/,""),reg=cmd=>state.meta.registry.find(e=>e.command===cmd&&(e.context===kindKey||e.context==="global"));
      const statements=(row.statements||[]).map(text=>{const cmd=String(text).trim().split(/\s+/)[0]||"",e=reg(cmd);
        return [el("span",{class:"mono",text:String(text)}),e?e.label:cmd,e?.status==="announced"?"announced for 5.41, not checked":e?`${e.status==="curated"?"checked":"documented"} · p.${e.page}`:"not in the pinned manual"];});
      const units=m.objects.filter(o=>o.kind==="monster");
      const compare=row.kind==="monster"&&units.length?(()=>{const s=select("compare-with",units.map(o=>[String(o.index),o.display]));s.setAttribute("aria-label","Unit to compare");
        return el("div",{class:"btn-row"},s,btn("Compare with this row",()=>{location.hash=path("p",m.project.slug,"units",s.value)+`?c=all&rev=${pinOf(m)}&refs=cat:${index}`;},"btn-small"));})():null;
      return stack(backToList||null,panel(row.name,
        table(["Provenance","Value"],[["Category",kinds[kindKey]?.[1]||row.kind],["ID",row.id!=null?`${row.id} (${row.id_source||"unknown source"})`:"—"],
          ["Source",row.source_file?`${row.source_file}:${row.source_line}`:"—"],["Game version",c.game_version],["Catalog",`${c.source==="snapshot"?"private snapshot":"configured file"} · ${short(c.sha256)}`]]),
        row.name_count>1?stateBox("warn","Duplicate name",`${row.name_count} rows share this name (this is ${row.name_ordinal+1}). File order is not proof of the game's selection offset.`):null,
        c.game_version!==m.project.target_version?stateBox("warn","Version differs",`This catalog describes game ${c.game_version}; the project targets ${m.project.target_version||"no version"}.`):null,
        statements.length?table(["Statement","Meaning","Manual"],statements):p("No statements recorded for this row.","faint"),
        row.multiline_commands?.length?p(`Strings continuing over line breaks: ${row.multiline_commands.join(", ")} (kept verbatim; engine reading not verified).`,"faint"):null,
        p("Only explicit commands printed in the reference file are shown. Copied values and game defaults are not resolved.","faint")),compare,
        !["monster","weapon","ritual"].includes(r.row.kind)?null:ambiguousCopy(r.row)?stack(stateBox("warn","Not available as a template.",ambiguousCopy(r.row)),link(`New ${kinds[r.row.kind][1].toLowerCase()}`,route(m,kinds[r.row.kind][2],"new"),"btn btn-ghost")):
          link("Use as template",route(m,kinds[r.row.kind][2],"new")+`${route(m,kinds[r.row.kind][2],"new").includes("?")?"&":"?"}template=${encodeURIComponent(index)}`,"btn"),
        r.used_in_project.length?panel("Used in this project",table(["Command","Source"],r.used_in_project.map(x=>[x.command,sourceLink(m,x.line)]))):null,
        details("JSON",el("pre",{class:"code",text:JSON.stringify(r.row,null,2)})));
    }
  }
  async function inspector(m,arg,index) {
    if(arg==="detail")return catalogDetail(m,index,link("← Back to catalog",route(m,"inspector")));
    const q=query(),args=new URLSearchParams(Object.entries(CAT_DEFAULTS).map(([k,v])=>[k,q.get(k)||v]));
    let sel=/^\d+$/.test(q.get("sel")||"")?Number(q.get("sel")):null,conditions=parseConditions(args.get("conditions"));
    let broken=conditions===null?"The filter conditions in this address are malformed or out of range.":null,r;
    const over=extra=>new URLSearchParams({...Object.fromEntries(args),...extra});
    // A rejected filter still fetches the unfiltered first page for categories and columns, but its rows are not shown.
    try{r=await get(`${base(m)}/catalog?${broken?over({conditions:"[]"}):args}`);}
    catch(e){if(e.code!=="bad_filter")throw e;broken=e.message;r=await get(`${base(m)}/catalog?${over({conditions:"[]"})}`);}
    if(!r.catalog.available)return stack(stateBox("empty","No local catalog.",r.catalog.note),link("Import reference files",route(m,"overview","catalog-import"),"btn"));
    const status=el("p",{class:"insp-status",role:"status","aria-live":"polite"}),results=el("div",{class:"insp-results"}),pager=el("div",{class:"btn-row insp-pager"});
    const pane=el("section",{class:"panel insp-pane","aria-label":"Catalog results"},status,results,pager);
    const detail=el("article",{class:"insp-detail sheet-view","aria-label":"Selected catalog row"},stateBox("empty","Choose a row.","Its source, provenance and statements appear here."));
    const search=input("catalog-search",args.get("q"),"search");search.id="catalog-search";search.placeholder="Search catalog  ( / )";search.setAttribute("aria-label","Search catalog");
    const category=select("category",[["","All categories"],...r.kinds.map(k=>[k,kinds[k]?.[0]||k])],args.get("kind"));category.setAttribute("aria-label","Category");
    const sort=select("sort",[["name","Name"],["id","ID"],["kind","Category"]],args.get("sort")),order=select("order",[["asc","Ascending"],["desc","Descending"]],args.get("order")),per=select("per",[["20","20"],["40","40"],["100","100"]],args.get("per"));
    const column=select("column",[["","Choose a column"],...(r.columns||[]).map(k=>[k,k])]),operator=select("operator",CAT_OPS),value=input("condition-value");
    const chipList=el("ul",{class:"plain-list chips","aria-label":"Active conditions"}),builderErr=el("p",{class:"field-err",role:"alert"});
    const add=btn("Add condition",()=>saveCondition(),"btn-small"),cancel=btn("Cancel edit",()=>{editing=null;resetBuilder();},"btn-small btn-ghost");cancel.hidden=true;
    const advanced=el("details",{class:"insp-adv",open:conditions?.length||broken?true:null},el("summary",{text:"Advanced: sort and conditions"}),
      el("div",{class:"btn-row"},field("Sort",sort),field("Direction",order),field("Page size",per)),
      el("h4",{text:"Conditions"}),chipList,el("div",{class:"btn-row"},field("Column",column),field("Condition",operator),field("Value",value),add,cancel),builderErr);
    let ticket=0,dticket=0,editing=null,timer,typing=false;
    const stacked=()=>matchMedia("(max-width: 1100px)").matches;
    // The address records non-default settings and the chosen row without re-rendering, so focus stays put. Discrete changes
    // (category, sort, paging, conditions, selection) push a history entry; one burst of typing in the search adds a single
    // entry that is then updated in place. Back and Forward re-render from the address (hashchange).
    function syncHash(mode="replace"){const qs=new URLSearchParams();for(const [k,v]of args)if(v!==CAT_DEFAULTS[k])qs.set(k,v);if(sel!==null)qs.set("sel",String(sel));
      const url=route(m,"inspector")+(String(qs)?`?${qs}`:"");
      if(url!==location.hash){if(mode==="push"||(mode==="typing"&&!typing))history.pushState(KENO_ENTRY,"",url);else history.replaceState(KENO_ENTRY,"",url);}
      typing=mode==="typing";}
    function showBroken(message){results.replaceChildren(stack(stateBox("error","Filters not applied.",`${message} No rows were filtered with them.`),
      el("div",{class:"btn-row"},btn("Reset filters (keep search)",()=>{conditions=[];broken=null;applyConditions();},"btn-small"),btn("Reset all",resetAll,"btn-small btn-ghost"))));
      pager.replaceChildren();status.textContent="Filters were rejected; reset them to see results.";}
    function fill(page){
      const list=el("ul",{class:"unit-list insp-list","aria-label":"Catalog rows"},page.rows.map(x=>el("li",null,el("a",{class:"unit-item",href:route(m,"inspector","detail",x.index),"data-index":x.index,
        "aria-current":x.index===sel?"true":null,onclick:e=>{e.preventDefault();choose(x.index);}},
        el("span",null,el("div",{class:"nm",text:x.name||"(unnamed)"}),el("div",{class:"sub",text:[kinds[String(x.kind).replace(/_selection$/,"")]?.[1]||x.kind,x.id!=null?`ID ${x.id}`:null,
          x.name_count>1?`duplicate ${x.name_ordinal+1} of ${x.name_count}`:null,x.source_file?`${x.source_file}:${x.source_line}`:null].filter(Boolean).join(" · ")}))))));
      list.addEventListener("keydown",e=>{if(!["ArrowUp","ArrowDown","Home","End"].includes(e.key))return;const links=[...list.querySelectorAll("a")],i=links.indexOf(document.activeElement);if(i<0)return;e.preventDefault();
        if(e.key==="ArrowUp"&&i===0)search.focus();else links[e.key==="Home"?0:e.key==="End"?links.length-1:Math.max(0,Math.min(links.length-1,i+(e.key==="ArrowDown"?1:-1)))].focus();});
      results.replaceChildren(page.rows.length?list:stateBox("empty","No rows match.","Change the search or conditions, or use Reset all."));
      status.textContent=`${page.total} result${page.total===1?"":"s"} · page ${page.page} of ${page.pages}${page.unverified?" · catalog version differs from the target":""}`;
      const go=n=>{args.set("page",String(n));refresh(true);};
      pager.replaceChildren(el("button",{type:"button",class:"btn btn-ghost btn-small",disabled:page.page<=1,onclick:()=>go(page.page-1)},"Previous"),
        el("span",{class:"insp-pageno faint",text:`${page.page} / ${page.pages}`}),el("button",{type:"button",class:"btn btn-ghost btn-small",disabled:page.page>=page.pages,onclick:()=>go(page.page+1)},"Next"));
    }
    async function refresh(keepPage=false,mode="push"){
      if(!keepPage)args.set("page","1");
      const mine=++ticket;pane.classList.add("is-updating");pane.setAttribute("aria-busy","true");status.textContent="Loading results…";syncHash(mode);
      try{const page=await get(`${base(m)}/catalog?${args}`);if(mine!==ticket||!pane.isConnected)return;fill(page);}
      catch(e){if(mine!==ticket)return;if(e.code==="bad_filter")showBroken(e.message);else{results.replaceChildren(errorBox(e,()=>refresh(true)));status.textContent="Results could not be loaded.";}}
      finally{if(mine===ticket){pane.classList.remove("is-updating");pane.removeAttribute("aria-busy");}}
    }
    async function choose(i,focus=true,mode="push"){
      sel=i;syncHash(mode);results.querySelectorAll("a[data-index]").forEach(a=>Number(a.dataset.index)===i?a.setAttribute("aria-current","true"):a.removeAttribute("aria-current"));
      const mine=++dticket;detail.classList.add("is-updating");detail.setAttribute("aria-busy","true");
      const back=btn("Back to results",()=>($(`a[data-index="${i}"]`,results)||search).focus(),"btn-small btn-ghost");
      try{const body=await catalogDetail(m,i,stacked()?back:null);if(mine!==dticket||!detail.isConnected)return;detail.replaceChildren(body);
        const h=$("h3",detail);if(h){h.tabIndex=-1;if(focus&&stacked()){h.scrollIntoView({block:"start"});h.focus({preventScroll:true});}}}
      catch(e){if(mine===dticket)detail.replaceChildren(errorBox(e,()=>choose(i,focus,"replace")),btn("Clear selection",()=>{sel=null;syncHash("push");detail.replaceChildren(stateBox("empty","Choose a row."));},"btn-small btn-ghost"));}
      finally{if(mine===dticket){detail.classList.remove("is-updating");detail.removeAttribute("aria-busy");}}
    }
    const opLabel=op=>CAT_OPS.find(x=>x[0]===op)?.[1]||op,noValue=op=>["exists","missing"].includes(op);
    function showChips(){chipList.replaceChildren(...(conditions||[]).map((cd,i)=>{const text=`${cd.field} ${opLabel(cd.op)}${noValue(cd.op)?"":` ${cd.value??""}`}`;
      const edit=btn("Edit",()=>{editing=i;column.value=cd.field;operator.value=cd.op;value.value=String(cd.value??"");value.disabled=noValue(cd.op);add.textContent="Update condition";cancel.hidden=false;column.focus();},"btn-small btn-ghost");
      const remove=btn("Remove",()=>{conditions.splice(i,1);if(editing===i){editing=null;resetBuilder();}applyConditions();(chipList.querySelector("button")||column).focus();},"btn-small btn-ghost");
      edit.setAttribute("aria-label",`Edit condition: ${text}`);remove.setAttribute("aria-label",`Remove condition: ${text}`);
      return el("li",{class:"btn-row"},el("span",{class:`badge ${editing===i?"warn":"info"}`,text}),edit,remove);}));
      if(!conditions?.length)chipList.append(el("li",{class:"faint",text:"No conditions."}));}
    function resetBuilder(){column.value="";operator.value="eq";value.value="";value.disabled=false;add.textContent="Add condition";cancel.hidden=true;builderErr.textContent="";}
    function applyConditions(){args.set("conditions",JSON.stringify(conditions||[]));showChips();refresh();}
    // A condition is checked here before it is added; the server repeats the same checks.
    function saveCondition(){builderErr.textContent="";const op=operator.value,v=value.value.trim();conditions=conditions||[];
      if(editing===null&&conditions.length>=8){builderErr.textContent="Use at most eight conditions; remove one first.";return;}
      if(!column.value)return invalid(column,"Choose a column.");
      if(!noValue(op)&&!v)return invalid(value,"Enter a value, or choose is present / is missing.");
      if(["gt","ge","lt","le"].includes(op)&&!Number.isFinite(Number(v)))return invalid(value,"Enter a number for this comparison.");
      if(v.length>120)return invalid(value,"Use at most 120 characters.");
      const cond={field:column.value,op,...(noValue(op)?{}:{value:v})};
      if(editing!==null)conditions[editing]=cond;else conditions.push(cond);editing=null;resetBuilder();applyConditions();column.focus();}
    function resetAll(){for(const [k,v]of Object.entries(CAT_DEFAULTS))args.set(k,v);conditions=[];broken=null;editing=null;
      search.value="";category.value="";sort.value="name";order.value="asc";per.value="40";resetBuilder();showChips();refresh();search.focus();}
    operator.addEventListener("change",()=>{value.disabled=noValue(operator.value);if(value.disabled)value.value="";});
    search.addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(()=>{args.set("q",search.value);refresh(false,"typing");},250);});
    search.addEventListener("keydown",e=>{if(e.key==="Escape"&&search.value){search.value="";args.set("q","");refresh();}if(e.key==="ArrowDown"){const a=$("a[data-index]",results);if(a){e.preventDefault();a.focus();}}});
    category.addEventListener("change",()=>{args.set("kind",category.value);refresh();});
    for(const [k,c]of [["sort",sort],["order",order],["per",per]])c.addEventListener("change",()=>{args.set(k,c.value);refresh();});
    if(history.state?.keno!==true)history.replaceState(KENO_ENTRY,"",location.hash);
    showChips();if(broken)showBroken(broken);else fill(r);if(sel!==null)choose(sel,false,"replace");
    // Back/Forward land on the row that was chosen in that entry, or on the search box.
    if(state.historyNav)state.focusTarget=sel!==null&&!broken?`.insp-results a[data-index="${sel}"]`:"#catalog-search";
    return stack(el("div",{class:"insp-tools"},el("div",{class:"insp-toolbar"},search,category,btn("Reset all",resetAll,"btn-small btn-ghost")),advanced),
      el("div",{class:"split"},pane,detail));
  }
  // ---------- catalog source and private snapshot ----------
  const SNAP_KIND={current:"ok",offline:"warn",stale:"warn",invalid:"err",unused:"info"};
  function catalogPanel(m,arg){
    const c=m.catalog,snap=c.snapshot,box=el("div"),actions=el("div",{class:"btn-row"});
    const run=(action,label)=>{const args={project:m.project.slug,expected_revision:m.revision,action};
      reviewWrite(m,{key:`${m.project.slug}:snapshot`,slug:m.project.slug,label},actions,box,"preview_catalog_snapshot",args,"apply_catalog_snapshot",args);};
    if(c.available&&c.source!=="snapshot"&&snap?.status!=="current")actions.append(btn(snap?"Review new snapshot":"Review snapshot",()=>run("capture","Catalog snapshot"),"btn-small"));
    if(snap)actions.append(btn("Review release of snapshot",()=>run("release","Catalog snapshot released"),"btn-small btn-ghost"));
    return panel("Local catalog",
      c.available?stack(p(`${c.rows} entries · game ${c.game_version} · ${c.source==="snapshot"?"read from the private snapshot":`configured file ${m.project.catalog}`}`),
        c.game_version!==m.project.target_version?el("p",null,badge("Catalog version differs","warn"),` The catalog describes game ${c.game_version}; the project targets ${m.project.target_version||"no version"}. Catalog matches stay unverified.`):null,
        p(String(c.provenance),"faint"),link("Open catalog",route(m,"inspector"))):p(c.note),
      snap?el("p",null,badge(`Snapshot: ${snap.status}`,SNAP_KIND[snap.status]||"info")," ",snap.note,el("span",{class:"faint mono",text:` ${short(snap.sha256)} · game ${snap.game_version}${snap.source?` · copied from ${snap.source}`:""}`})):
        c.available?p("No private snapshot. A snapshot is an exact copy of the configured catalog kept in this project's private folder, so references stay checkable if the catalog file changes or moves. It is part of the project revision and never exported.","faint"):null,
      actions,box,
      arg==="catalog-import"?panel("Import reference catalog",catalogImport(m)):details("Import reference catalog",catalogImport(m)));
  }
  // ---------- faction design checklist (docs/FACTION-DESIGN.md): authoring reminders from the saved model ----------
  function factionChecklist(m,open){
    const classes=m.objects.filter(o=>o.kind==="class"),units=m.objects.filter(o=>o.kind==="monster"),rituals=m.objects.filter(o=>o.kind==="ritual");
    const v=o=>o.view||{},art=artworkSummary(m);
    const rows=[
      ["Class identity",classes.length&&classes.every(c=>v(c).setclassname&&v(c).classdescr),classes.length?`${classes.filter(c=>v(c).setclassname&&v(c).classdescr).length} of ${classes.length} classes have a name and description.`:"No class yet.","classes"],
      ["Economy and recruitment",classes.length&&classes.every(c=>Object.values(v(c).recruitment||{}).some(r=>r.length)),`${classes.reduce((n,c)=>n+Object.values(v(c).recruitment||{}).reduce((a,r)=>a+r.length,0),0)} recruitment rows; check chances, counts, gold and iron in Design.`,"design"],
      ["Starting citadel and forces",classes.length&&classes.every(c=>v(c).hometerr?.target?.citadel&&v(c).main_commander&&v(c).army?.some(a=>a.units.length)),"A home terrain number alone does not prove a valid citadel; starting commander and troops are listed per class in Design.","design"],
      ["Ritual schools and resources",rituals.length>0,`${rituals.length} rituals · ${m.counts.school} new ritual schools. Presence only: check starting knowledge or learning, caster level, costs and results.`,"rituals"],
      ["Alternate forms",null,`${units.filter(u=>v(u).forms?.length).length} units declare forms (resolved by source order, manual p.18).`,"units"],
      ["Planes, terrain and events",null,`${classes.filter(c=>v(c).startplane).length} classes set a start plane · ${m.counts.terrain} terrain · ${m.counts.event} events.`,"terrain"],
      ["Original artwork",art.kind==="ok",art.text,null,route(m,"overview","artwork")],
      ["Evidence kept separately",null,"Static, browser, packaging and game observations are recorded separately in Evidence; none proves balance.","evidence"]];
    const list=el("ul",{class:"ready-list"},rows.map(([label,ok,text,tab,href])=>el("li",{class:`ready-row is-${ok===null?"info":ok?"ok":"warn"}`},
      ok===null?el("span",{"aria-hidden":"true"}):badge(ok?"Present":"Check",ok?"ok":"warn"),el("span",{class:"ready-label",text:label}),el("span",{class:"ready-text",text:text}),
      el("span",{class:"ready-action"},link("Open",href||route(m,tab))))));
    const body=stack(p("A CoE5 faction is a class with its identity, economy, home and starting army, rituals, forms and original artwork. These reminders come from the saved source; they are not a balance check. Present means a part exists in the source; it does not show that its economy, progression or acquisition routes are complete.","faint"),list,
      el("p",{class:"faint"},"Guide: ",link("FACTION-DESIGN",path("docs","FACTION-DESIGN.md"))," · ",link("Design workspace",route(m,"design"))));
    return open?el("section",{class:"panel","aria-labelledby":"faction-h"},el("h3",{id:"faction-h",text:"Faction design checklist"}),body):details("Faction design checklist",body);
  }
  // ---------- design workspace: authored roster, economy, start and rituals per class; no score ----------
  async function designView(m){
    const cls=scope(),index=/^\d+$/.test(cls)?Number(cls):null;
    if(!m.objects.some(o=>o.kind==="class"))return stack(stateBox("empty","No class yet.","A faction starts with a class: create one, then add its units, home citadel and recruitment."),link("New class",route(m,"classes","new"),"btn"));
    const r=await api("design_report",{project:m.project.slug,class_index:index});
    const ref=x=>x?reference(m,x):"—";
    // Source of the citadel answer: this mod, the local catalog (with its game version), or explicitly unknown.
    const citadel=t=>{const e=t.citadel_evidence||{},cat=e.source==="catalog"?`catalog, game ${e.game_version}${e.version_mismatch?", not the target version":""}`:null;
      return e.status==="local"?` · citadel (this mod, line ${e.line})`:e.status==="catalog"?` · citadel (${cat})`:
        e.status==="not_marked"?` · not marked citadel${cat?` (${cat})`:""}`:e.status==="cleared"?` · ${e.command} on line ${e.line}: citadel unresolved`:
        ` · citadel ${e.status==="ambiguous"?"ambiguous":"unresolved"}`;};
    return stack(p("Authored values with their source lines. Nothing here scores balance or simulates recruitment rolls; verify behavior in the game and record it in Evidence.","faint"),
      classCompare(m,index),
      ...r.classes.map(c=>{const o=m.objects.find(x=>x.index===c.index);
        return el("section",{class:"panel design-class","aria-labelledby":`design-${c.index}`},el("h3",{id:`design-${c.index}`},o?objectLink(m,o):c.name," ",el("span",{class:"faint",text:`line ${c.line}`})),
          el("ul",{class:"ready-list"},c.checks.map(k=>el("li",{class:`ready-row is-${k.ok?"ok":"warn"}`},badge(k.ok?"Set":"Check",k.ok?"ok":"warn"),el("span",{class:"ready-label",text:k.label}),el("span",{class:"ready-text",text:k.detail})))),
          table(["Home","Value"],[["Home citadel terrain",c.home.target?[ref(c.home.target),citadel(c.home.target)]:c.home.hometerr||"Not set"],["Start plane",c.home.startplane??"Not set"],
            ["Start-plane citadel",c.home.createcit??"Not set"],["Gold income bonus %",c.home.goldbonus??"Not set"],["Iron income bonus %",c.home.ironbonus??"Not set"]]),
          panel("Starting forces",c.main_commander?el("p",null,"Main commander: ",ref(c.main_commander)," · ",sourceLink(m,c.main_commander.line)):p("No main commander.","faint"),
            c.army.length?table(["Commander","Units","Source"],c.army.map(a=>[a.commander?ref(a.commander):"Before addstartcom (squad not modelled)",a.units.map((u,i)=>[i?", ":"",u.count," × ",ref(u.monster)]),sourceLink(m,a.line)])):p("No starting units.","faint"),
            c.start_terrain.length?p(`Starting terrain: ${c.start_terrain.map(t=>t.name||t.value).join(", ")}`):null),
          panel("Recruitment",c.recruitment.length?table(["Unit","Group","Chance %","Count","Gold","Gold die","Iron","Extra costs","Source"],c.recruitment.map(x=>[ref(x.reference),x.group,x.chance,x.count??"—",x.gold,x.gold_die,x.iron,
            x.extra_costs.map(e=>`${e.amount} ${e.resource}`).join(", ")||"—",sourceLink(m,x.line)])):p("No recruitment rows.","faint"),
            p("Gold die is shown as written; how the game rolls it is not modelled here.","faint")),
          panel("Rituals reachable through class units",c.schools.length?p(`Schools: ${c.schools.map(s=>`${s.school} (via ${[...new Set(s.via.map(v=>v.unit))].join(", ")})`).join("; ")}`):p("No class unit has power or allrit in this mod.","faint"),
            c.rituals.length?table(["Ritual","School","Level","Costs","Summons"],c.rituals.map(x=>{const ro=m.objects.find(y=>y.index===x.index);return [ro?objectLink(m,ro):x.name,x.school,x.level??"?",x.costs.map(k=>`${k.amount} ${k.resource}`).join(", ")||(x.free?"free":"—"),x.summons.join(", ")||"—"];})):null,
            c.ritual_resources.length?p(`Resources used: ${c.ritual_resources.map(x=>`${x.resource} (${x.rituals.length})`).join(", ")}`,"faint"):null),
          details(`Roster (${c.roster.length})`,table(["Unit","Role","Artwork"],c.roster.map(u=>{const uo=m.objects.find(y=>y.index===u.index);return [uo?objectLink(m,uo):u.name,u.form_only?"alternate form":u.role,u.art||"—"];}))));}),
      el("ul",{class:"art-notes"},r.notes.map(n=>el("li",{text:n}))));
  }
  // Class beside other local classes or catalog class rows (compare_classes). The comparison lives in the address
  // (?cmp=<class index>&crefs=u:3,cat:12), separate from the class scope (?c=) and from unit references (?refs=), so reload,
  // Back and shared links reproduce it. Address tokens are checked before use; malformed or removed ones are listed, not used.
  // Cells are as written or printed; ? marks unknown or partial coverage and is never treated as zero.
  const classLinkTokens=()=>[...new Set((query().get("crefs")||"").split(",").map(x=>x.trim()).filter(Boolean))].slice(0,12);
  function classCompare(m,scoped){
    const classes=m.objects.filter(o=>o.kind==="class"),key=`${m.project.slug}:class-compare`;
    const c=state.filters.get(key)||{base:"",refs:[],invalid:[],result:null,resultFor:"",linked:null};state.filters.set(key,c);
    if(!c.invalid)c.invalid=[];
    // Catalog rows and local classes both belong to the chosen revision; a fresh page starts the selection again.
    if(c.rev&&c.rev!==pinOf(m)){c.base="";c.refs=[];c.invalid=[];c.result=null;c.resultFor="";c.linked=null;}
    c.rev=pinOf(m);
    for(const r of c.refs)if(r.object_index!==undefined)r.label=classes.find(x=>x.index===r.object_index)?.display||r.label;
    const guard=state.linkGuard||{},stale=guard.status==="stale"&&guard.classes>0,legacy=guard.status==="legacy"&&guard.classes>0;
    const defaultBase=String(scoped??classes[0].index),linkBase=stale?null:query().get("cmp"),tokens=stale?[]:classLinkTokens();
    const linkKey=`${linkBase??""}|${tokens.join(",")}`,fromAddress=(linkBase!==null||tokens.length>0)&&linkKey!==c.linked;
    if(!classes.some(x=>String(x.index)===c.base))c.base=defaultBase;
    const box=el("div",{"aria-live":"polite"}),chips=el("ul",{class:"plain-list chips","aria-label":"Classes to compare"}),hits=el("div"),recovery=el("div"),limit=el("p",{class:"field-meta",role:"status"});
    const baseSel=select("class-compare-base",classes.map(x=>[String(x.index),`${x.display} (line ${x.line})`]),c.base);
    const local=select("class-compare-local",[["","Choose another class of this project"],...classes.map(x=>[String(x.index),`${x.display} (line ${x.line})`])]);
    const token=r=>r.object_index!==undefined?`u:${r.object_index}`:`cat:${r.catalog_index}`;
    const current=()=>c.refs.map(token).join(",");
    let classTicket=0;
    const classResultKey=()=>`${m.revision}|${c.base}|${current()}`;
    // The address follows the chosen classes without re-rendering; an untouched default comparison leaves it clean.
    // A chosen comparison is pinned to the saved revision (?rev=); an unchecked older link stays unpinned until the user acts.
    function syncUrl(pin=true){const q=new URLSearchParams(query());
      if(c.refs.length||c.base!==defaultBase){q.set("cmp",c.base);if(c.refs.length)q.set("crefs",current());else q.delete("crefs");if(pin||!legacy)q.set("rev",pinOf(m));}
      else{q.delete("cmp");q.delete("crefs");}
      history.replaceState(null,"",path(...parts())+`?${q}`);c.linked=`${q.get("cmp")??""}|${q.get("crefs")||""}`;}
    // Selection changes clear old class results and invalidate outstanding comparison responses.
    function invalidateClasses(){classTicket++;c.result=null;c.resultFor="";run.disabled=false;box.replaceChildren();}
    const addRef=r=>{if(c.refs.length>=4){limit.textContent="Compare at most four classes; remove one first.";return;}limit.textContent="";
      if(String(r.object_index)===c.base){limit.textContent="That is the class being compared.";return;}
      if(!c.refs.some(x=>token(x)===token(r))){c.refs.push(r);invalidateClasses();}syncUrl();showChips();};
    function showChips(){chips.replaceChildren(...c.refs.map((r,i)=>{const b=btn(`${r.label} ×`,()=>{c.refs.splice(i,1);invalidateClasses();limit.textContent="";syncUrl();showChips();},"btn-small btn-ghost");
      b.setAttribute("aria-label",`Remove ${r.label} from the class comparison`);return el("li",null,b);}));if(!c.refs.length)chips.append(el("li",{class:"faint",text:"No classes chosen."}));}
    function clearAll(){c.refs=[];c.invalid=[];c.base=defaultBase;baseSel.value=c.base;invalidateClasses();syncUrl();showChips();showRecovery();local.focus();}
    function showRecovery(){recovery.replaceChildren(c.invalid.length?stack(stateBox("warn","Some classes in this link cannot be compared.","They were not used. Remove them to compare the rest, or start again."),
      el("ul",null,c.invalid.map(x=>el("li",null,el("span",{class:"mono",text:x.token})," — ",x.reason))),
      el("div",{class:"btn-row"},btn(c.refs.length?"Remove them and compare the rest":"Remove them",()=>{c.invalid=[];syncUrl();showRecovery();if(c.refs.length)runCompare();},"btn-small"),
        btn("Clear comparison",clearAll,"btn-small btn-ghost"))):"");}
    // Address tokens become references: local classes are checked against this model, catalog rows against the catalog.
    async function fromLink(){
      const refs=[],invalidRefs=[],pending=[];
      if(linkBase!==null){if(/^\d{1,6}$/.test(linkBase)&&classes.some(x=>String(x.index)===linkBase))c.base=linkBase;
        else{c.base=defaultBase;invalidRefs.push({token:`cmp=${linkBase.slice(0,40)}`,reason:"Not a class of this project's saved revision; the scoped or first class is used instead."});}}
      baseSel.value=c.base;
      tokens.forEach((t,i)=>{let mt;
        if(i>=4)invalidRefs.push({token:t.slice(0,40),reason:"More than four classes."});
        else if((mt=t.match(/^u:(\d{1,6})$/))){const x=classes.find(y=>y.index===Number(mt[1]));
          if(x&&String(x.index)!==c.base)refs.push({object_index:x.index,label:x.display});
          else invalidRefs.push({token:t,reason:x?"This is the class being compared.":"Not a class of this project's saved revision."});}
        else if((mt=t.match(/^cat:(\d{1,7})$/))){const r={catalog_index:Number(mt[1]),label:`Catalog row ${mt[1]}`};refs.push(r);pending.push([t,r]);}
        else invalidRefs.push({token:t.slice(0,40),reason:"Not a recognised class reference (use u:<class> or cat:<catalog row>)."});});
      c.refs=refs;c.invalid=invalidRefs;c.linked=linkKey;c.result=null;showChips();showRecovery();
      const request=++classTicket;
      if(pending.length)box.replaceChildren(stateBox("loading","Checking catalog classes…"));
      await Promise.all(pending.map(async([t,r])=>{try{const row=(await get(`${base(m)}/catalog/${r.catalog_index}`)).row;
        if(request!==classTicket||!box.isConnected)return;
        if(!["class","class_selection"].includes(row.kind))throw new Error("That catalog row is not a class.");
        r.label=`${row.name||r.catalog_index} (catalog ${row.kind==="class_selection"?"selection":"class"})`;}
        catch(e){if(request!==classTicket||!box.isConnected)return;c.refs=c.refs.filter(x=>x!==r);c.invalid.push({token:t,reason:e.code==="not_found"?"Not a row of the configured catalog (it may be missing or changed).":e.message});}}));
      if(request!==classTicket||!box.isConnected)return;
      box.replaceChildren();showChips();showRecovery();if(c.refs.length&&!c.invalid.length)runCompare();
    }
    baseSel.addEventListener("change",()=>{limit.textContent="";c.base=baseSel.value;c.refs=c.refs.filter(r=>String(r.object_index)!==c.base);invalidateClasses();syncUrl();showChips();});
    const search=input("class-compare-catalog","","search");search.placeholder="Search catalog classes";search.setAttribute("aria-label","Search catalog classes");
    let timer,ticket=0;search.addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(async()=>{const mine=++ticket,q=search.value.trim();if(!q){hits.replaceChildren();return;}
      try{const pages=await Promise.all(["class","class_selection"].map(kind=>get(`${base(m)}/catalog?${new URLSearchParams({q,kind,per:"10"})}`)));if(mine!==ticket)return;
        const rows=pages.flatMap(x=>x.rows);
        hits.replaceChildren(!pages[0].catalog.available?p(pages[0].catalog.note,"faint"):rows.length?el("ul",{class:"plain-list"},rows.map(row=>el("li",null,
          btn(`Add ${row.name||`catalog class ${row.index}`}${row.kind==="class_selection"?" (selected class)":""}`,()=>addRef({catalog_index:row.index,label:`${row.name||row.index} (catalog ${row.kind==="class_selection"?"selection":"class"})`}),"btn-small btn-ghost"),
          row.source_file?el("span",{class:"faint",text:` ${row.source_file}:${row.source_line}`}):null))):p("No catalog classes match.","faint"));}
      catch(e){if(mine===ticket)hits.replaceChildren(errorBox(e));}},300);});
    const run=btn("Compare classes",()=>runCompare());
    async function runCompare(){if(!c.refs.length){box.replaceChildren(stateBox("error","Choose at least one class to compare.","Add another class of this project or a catalog class."));return;}
      run.disabled=true;box.replaceChildren(stateBox("loading","Comparing classes…"));syncUrl(false);const request=++classTicket,forKey=classResultKey();
      try{const result=await api("compare_classes",{project:m.project.slug,class_index:Number(c.base),references:c.refs.map(({label,...r})=>r)});if(request!==classTicket||forKey!==classResultKey())return;if(result.revision!==m.revision)throw failure("stale_revision","The saved project changed. Reload it and choose the comparison again.");c.result=result;c.resultFor=forKey;show();}
      catch(e){if(request!==classTicket)return;box.replaceChildren(stack(errorBox(e,e.code==="stale_revision"?()=>{state.models.delete(m.project.slug);render();}:null),["bad_reference","not_found","bad_object"].includes(e.code)?p("A chosen class is no longer available in the saved project or catalog. Remove it, or clear the comparison.","faint"):null,
        btn("Clear comparison",clearAll,"btn-small btn-ghost")));}finally{if(request===classTicket)run.disabled=false;}}
    function show(){const r=c.result;if(!r)return;
      const cellNode=x=>x.value==null?el("div",null,el("span",{class:"unknown",text:"?"}),x.note?el("div",{class:"faint",text:x.note}):null):el("div",null,x.value,x.note?el("div",{class:"faint",text:x.note}):null);
      box.replaceChildren(stack(r.dashboard?classDashboard(m,r.dashboard):null,
        el("h4",{text:"Detailed comparison"}),
        el("div",{class:"table-wrap",tabindex:"0",role:"region","aria-label":"Class comparison (scrolls sideways on narrow screens)"},el("table",{class:"data"},
          el("caption",{text:"As written in this mod or printed in the catalog. ? is unknown or not covered, never zero."}),
          el("thead",null,el("tr",null,el("th",{scope:"col",text:"Value"}),r.columns.map((col,i)=>el("th",{scope:"col"},el("div",null,el("strong",{text:col.name}),
            el("div",{class:"faint",text:i===0?"This class":col.type==="catalog"?`Catalog · game ${col.game_version} · ${col.provenance}`:`This project · ${col.provenance}`}),
            col.coverage==="partial"?badge("partial coverage","warn"):null))))),
          el("tbody",null,r.rows.map(row=>el("tr",null,el("th",{scope:"row",text:row.label}),row.cells.map(x=>el("td",null,cellNode(x)))))))),
        ...r.columns.flatMap(col=>(col.warnings||[]).map(w=>stateBox("warn",`${col.name}: coverage`,w))),
        el("ul",{class:"art-notes"},r.notes.map(n=>el("li",{text:n})))));}
    showChips();showRecovery();
    // A stale class comparison in the address is not applied, and nothing from memory is compared in its place.
    const linkNote=stale?stack(stateBox("error","The class comparison in this link was not applied.",
        `It names ${linkWhat(guard)} of revision ${String(guard.pin).slice(0,16)}; the saved project is now ${short(m.revision)}, and classes may have been added, removed or moved since. Choose the classes again.`),
        el("div",{class:"btn-row"},btn("Clear comparison",clearAll,"btn-small btn-ghost"))):
      legacy?stateBox("warn","Check this class comparison: the link does not record which revision it was made for.","Its classes are named by their position in the saved source. Check the class names below; changing the selection records the saved revision in the address."):null;
    if(fromAddress)fromLink();
    else if(!stale&&c.result&&c.resultFor===classResultKey())show();
    else if(!stale&&c.refs.length&&!c.invalid.length&&c.linked)runCompare();
    const node=details("Compare classes",p("Side by side: roster variety, recruitment chances, counts, gold, gold die, iron and extra costs as written, recruitable units' explicit stats, income bonuses and ritual schools reached through the class's units. No score and no recruitment roll simulation. The address keeps your chosen classes, so you can reload or share the link.","faint"),
      el("div",{class:"btn-row"},field("Class to compare",baseSel),field("Another class of this project",local),
        btn("Add class",()=>{const x=classes.find(y=>String(y.index)===local.value);if(x)addRef({object_index:x.index,label:x.display});},"btn-small")),
      field("Catalog class",search,"Catalog class rows list their own explicit commands only; their units' rituals count only where a unit name is unique in the catalog."),hits,chips,limit,linkNote,recovery,run,box);
    node.open=c.refs.length>0||c.invalid.length>0||fromAddress||stale||legacy;return node;
  }
  // ---------- class comparison dashboard (compare_classes.dashboard): DOM and inline SVG, no chart library ----------
  // Each series keeps one letter, one marker shape and one colour slot in every chart, so identity never rests on colour;
  // every chart repeats its figures as text, and exact values sit in tables. Unknown values are counted, never drawn as zero.
  const SVGNS="http://www.w3.org/2000/svg";
  const svg=(tag,attrs,...kids)=>{const n=document.createElementNS(SVGNS,tag);for(const [k,v]of Object.entries(attrs||{}))if(v!==null&&v!==undefined)n.setAttribute(k,String(v));
    for(const k of kids.flat())if(k!==null&&k!==undefined)n.append(k instanceof Node?k:document.createTextNode(String(k)));return n;};
  const SHAPES=["circle","square","triangle","diamond","triangle-down"];
  function shape(i,cx,cy,r,title){
    const s=SHAPES[i%SHAPES.length],cls=`dash-mark s${i}`,t=title?svg("title",null,title):null;
    if(s==="circle")return svg("circle",{cx,cy,r,class:cls},t);
    if(s==="square")return svg("rect",{x:cx-r*.85,y:cy-r*.85,width:r*1.7,height:r*1.7,rx:1,class:cls},t);
    const pts=s==="triangle"?[[cx,cy-r],[cx+r,cy+r*.8],[cx-r,cy+r*.8]]:s==="triangle-down"?[[cx-r,cy-r*.8],[cx+r,cy-r*.8],[cx,cy+r]]:[[cx,cy-r*1.1],[cx+r*1.1,cy],[cx,cy+r*1.1],[cx-r*1.1,cy]];
    return svg("polygon",{points:pts.map(p=>p.join(",")).join(" "),class:cls},t);
  }
  const seriesKey=(i,s)=>el("span",{class:"dash-key"},svg("svg",{width:14,height:14,viewBox:"0 0 14 14","aria-hidden":"true",class:"dash-key-mark"},shape(i,7,7,5)),
    el("strong",{class:"dash-letter",text:s.marker}));
  const seriesLabel=(i,s)=>el("span",{class:"dash-series"},seriesKey(i,s),el("span",{class:"dash-name",text:s.name}));
  const num=v=>v!==null&&v!==undefined&&/^-?\d+$/.test(String(v))?Number(v):null;
  function classDashboard(m,dash){
    const cols=dash.columns,source=(col,u)=>col.type==="local"?(u.line?sourceLink(m,u.line):"authored"):
      col.catalog_index!=null?link(col.provenance,route(m,"inspector","detail",col.catalog_index)):col.provenance;
    const legend=el("ul",{class:"dash-legend","aria-label":"Series"},cols.map((s,i)=>el("li",null,seriesLabel(i,s),
      el("span",{class:"faint",text:` ${i===0?"this class":s.type==="catalog"?`catalog · game ${s.game_version}`:"this project"} · ${s.provenance}`}),
      s.recruitment_complete?null:[" ",badge("partial","warn")])));
    // Horizontal bars count names as written; hatching identifies rows whose wider class coverage is unknown.
    const metrics=[["troops","Recruitable troop types (addunitrec)"],["commanders","Recruitable commander types (addcomrec)"],["mercenaries","Mercenary types (addmercrec)"],["start_unit_types","Starting unit types (addstartunits)"]];
    const most=Math.max(1,...cols.flatMap(s=>metrics.map(([k])=>s.roster[k]||0)));
    const roster=el("section",{class:"dash-block","aria-labelledby":"dash-roster-h"},el("h5",{id:"dash-roster-h",text:"Roster variety"}),
      p("Distinct unit names per recruitment group, as written. A hatched bar covers only this block or catalog row. Other selection blocks and game defaults are not merged.","faint"),
      metrics.map(([k,label])=>el("div",{class:"dash-group",role:"group","aria-label":label},el("div",{class:"dash-group-label",text:label}),
        cols.map((s,i)=>{const n=s.roster[k],text=s.recruitment_complete?String(n):`${n} written (partial)`;
          return el("div",{class:"dash-bar-row"},seriesKey(i,s),el("span",{class:"dash-bar-track","aria-hidden":"true"},
            el("span",{class:`dash-bar s${i}${s.recruitment_complete?"":" is-partial"}`,style:null,"data-w":String(n/most)})),
            el("span",{class:"dash-bar-value",text}),el("span",{class:"sr-only",text:` ${s.name}`}));}))));
    roster.querySelectorAll(".dash-bar").forEach(b=>{b.style.width=`${Math.max(0,Math.min(1,Number(b.dataset.w)))*100}%`;});
    // One strip per series on a shared scale: each mark is one recruitment row (or unit); the text gives range and unknowns.
    function strips(title,id,intro,values,unitLabel){
      const all=cols.flatMap((s,i)=>values(s,i).map(v=>v.value)).filter(v=>v!==null);
      const lo=Math.min(0,...all),hi=Math.max(1,...all),W=300,pad=10,x=v=>pad+(v-lo)/(hi-lo||1)*(W-2*pad);
      return el("section",{class:"dash-block","aria-labelledby":id},el("h5",{id,text:title}),intro?p(intro,"faint"):null,
        el("div",{class:"dash-strips"},cols.map((s,i)=>{const vs=values(s,i),known=vs.filter(v=>v.value!==null),unknown=vs.length-known.length;
          const range=known.length?(()=>{const ns=known.map(v=>v.value),a=Math.min(...ns),b=Math.max(...ns);return a===b?`${a}`:`${a}–${b}`;})():"no known values";
          const summary=`${range} · ${known.length} ${unitLabel}${known.length===1?"":"s"}${unknown?` · ${unknown} unknown`:""}`;
          return el("div",{class:"dash-strip-row"},seriesLabel(i,s),
            svg("svg",{viewBox:`0 0 ${W} 24`,class:"dash-strip",role:"img","aria-label":`${s.marker} ${s.name}: ${summary}`,preserveAspectRatio:"xMidYMid meet"},
              svg("line",{x1:pad,x2:W-pad,y1:12,y2:12,class:"dash-axis"}),
              known.length>1?svg("line",{x1:x(Math.min(...known.map(v=>v.value))),x2:x(Math.max(...known.map(v=>v.value))),y1:12,y2:12,class:`dash-range s${i}`}):null,
              known.map(v=>shape(i,x(v.value),12,5,`${s.marker} ${s.name} · ${v.label}: ${v.value}`))),
            el("span",{class:"dash-strip-text",text:summary}));})),
        el("div",{class:"dash-scale faint","aria-hidden":"true"},el("span",{text:String(lo)}),el("span",{text:String(hi)})));
    }
    const rowValues=key=>s=>s.units.filter(u=>key!=="count"||u.group!=="commander").map(u=>({value:num(u[key]),label:`${u.unit} (${u.group})`}));
    const costs=el("div",{class:"dash-grid"},
      strips("Gold per row","dash-gold","Base gold argument of each recruitment row.",rowValues("gold"),"row"),
      strips("Gold die per row","dash-golddie","The row's gold-die argument as written; not rolled here.",rowValues("gold_die"),"row"),
      strips("Iron per row","dash-iron",null,rowValues("iron"),"row"),
      strips("Chance % per row","dash-chance","Raw chance argument; not a probability simulation.",rowValues("chance"),"row"));
    const stats=el("div",{class:"dash-grid"},dash.stat_keys.map(([k,label])=>strips(label,`dash-stat-${k}`,null,
      s=>s.units.map(u=>({value:num(u.stats[k].value),label:`${u.unit} (${u.group}, ${u.stats_from})`})),"unit")));
    const resources=s=>s.rituals.resources===null?el("span",{class:"unknown",text:"? not matched"}):s.rituals.resources.length?s.rituals.resources.map(x=>`${x.resource} (${x.rituals})`).join(", "):"none";
    const access=table(["Series","Gold income bonus %","Iron income bonus %","Ritual schools through units","Rituals in this mod","Ritual resources"],
      cols.map((s,i)=>[seriesLabel(i,s),s.income.goldbonus??el("span",{class:"unknown",text:"?"}),s.income.ironbonus??el("span",{class:"unknown",text:"?"}),
        s.rituals.schools.length?s.rituals.schools.join(", "):el("span",{class:"faint",text:s.rituals.coverage==="partial"?"none stated (partial)":"none stated"}),
        s.rituals.rituals??el("span",{class:"unknown",text:"?"}),resources(s)]));
    const cell=v=>v===null||v===undefined||v===""?el("span",{class:"unknown",text:"?"}):String(v);
    const exact=table(["Series","Unit","Group","Chance %","Count","Gold","Gold die","Iron","Extra costs",...dash.stat_keys.map(([,l])=>l),"Stats from","Source"],
      cols.flatMap((s,i)=>s.units.map(u=>[seriesKey(i,s),u.unit??"?",u.group,cell(u.chance),u.group==="commander"?"—":cell(u.count),cell(u.gold),cell(u.gold_die),cell(u.iron),
        u.extra_costs.map(x=>`${x.amount??"?"} ${x.resource||x.raw}`).join(", ")||"—",...dash.stat_keys.map(([k])=>{const st=u.stats[k],note=[st.source,st.via?`via ${st.via}`:null,st.line?`line ${st.line}`:null,st.note].filter(Boolean).join(" · ");return el("span",{class:st.value==null?"unknown":null,title:note},st.value!=null&&st.line&&["authored","donor"].includes(st.source)?sourceLink(m,st.line,String(st.value)):String(st.value??"?"));}),
        u.stats_from,source(s,u)])));
    const exactWrap=el("div",{class:"table-wrap",tabindex:"0",role:"region","aria-label":"Exact recruitment and stat values (scrolls sideways on narrow screens)"},exact.querySelector("table"));
    return el("section",{class:"panel dash","aria-labelledby":"dash-h"},el("h4",{id:"dash-h",text:"Comparison overview"}),
      p("Figures as written in this mod or printed in the catalog. Marks are recruitment rows or recruitable units; ? and unknown counts are never drawn as zero. This is not a balance score.","faint"),
      legend,roster,el("h5",{text:"Recruitment cost context"}),costs,el("h5",{text:"Recruitable units' explicit stats"}),stats,
      el("section",{class:"dash-block","aria-labelledby":"dash-access-h"},el("h5",{id:"dash-access-h",text:"Income and ritual access"}),access),
      details("Exact values per recruitment row",exactWrap),
      details("How to read these figures",el("ul",null,dash.help.map(t=>el("li",{text:t})))));
  }
  // ---------- evidence: private, revision-linked observations; never exported, never "engine verified" ----------
  async function evidenceView(m){
    const r=await api("list_evidence",{project:m.project.slug});
    const d=draft(`${m.project.slug}:evidence`,{slug:m.project.slug,label:"Evidence record",href:route(m,"evidence"),values:{category:"browser",summary:"",details:"",reference:""},observation:{}});
    if(!d.observation)d.observation={};
    if(!Array.isArray(d.references))d.references=[];
    const form=el("form",{class:"stack"}),box=el("div");
    const category=select("category",Object.entries(r.categories),d.values.category);
    const summary=input("summary",d.values.summary);summary.maxLength=200;summary.required=true;
    const det=area("details",d.values.details,4);det.maxLength=4000;const refIn=input("reference",d.values.reference);refIn.maxLength=200;
    for(const [k,c] of [["summary",summary],["details",det],["reference",refIn]])c.addEventListener("input",()=>{d.values[k]=c.value;dirty(d);});
    // Optional structured fields, shown and sent only for a user-reported game observation; values are the user's own report.
    const obsLimits={game_version:40,tester:80,class_played:120,opponents:200,map:120,outcome:200},obsInputs={},classNames=m.objects.filter(o=>o.kind==="class").map(o=>o.display);
    const classList=el("datalist",{id:"evidence-classes"},classNames.map(n=>el("option",{value:n})));
    const obsGrid=el("div",{class:"edit-grid"},OBS_LABELS.map(([k,label])=>{const c=input(`obs-${k}`,d.observation[k]??"",k==="turns"?"number":"text");
      if(k==="turns"){c.min="0";c.max="100000";c.step="1";}else c.maxLength=k==="reference_sha256"?64:obsLimits[k];
      if(k==="class_played")c.setAttribute("list","evidence-classes");if(k==="reference_sha256"){c.classList.add("mono");c.spellcheck=false;}
      c.addEventListener("input",()=>{d.observation[k]=c.value;dirty(d);});obsInputs[k]=c;
      return field(`${label} (optional)`,c,k==="game_version"?"The version you played, as shown by the game; KENOGENESIS does not check it.":k==="reference_sha256"?"SHA-256 of a screenshot, log or save you keep privately (64 hex characters). The file is not attached.":null);}));
    const obsBox=el("fieldset",{class:"edit-group"},el("legend",{text:"Game observation details"}),
      stateBox("warn","User reported","You observed this in Conquest of Elysium 5 yourself. KENOGENESIS did not launch, run or watch the game, and the record never marks the mod as verified."),obsGrid,classList);
    // Up to max_references typed references; each row keeps its index so a server field error names the same row.
    const kindsList=Object.entries(r.reference_kinds||{}),maxRefs=r.max_references||8,refRows=el("div",{class:"stack"}),refStatus=el("p",{class:"field-meta",role:"status","aria-live":"polite"});
    const addRefBtn=btn("Add a reference",()=>{if(d.references.length>=maxRefs)return;d.references.push({kind:kindsList[0]?.[0]||"other",label:"",sha256:""});dirty(d);showRefs();
      refRows.querySelector(`[name="ref-label-${d.references.length-1}"]`)?.focus();},"btn-small btn-ghost");
    function showRefs(){refRows.replaceChildren(...d.references.map((x,i)=>{
      const kind=select(`ref-kind-${i}`,kindsList,x.kind),label=input(`ref-label-${i}`,x.label),sha=input(`ref-sha256-${i}`,x.sha256);
      label.maxLength=200;sha.maxLength=64;sha.classList.add("mono");sha.spellcheck=false;
      kind.addEventListener("change",()=>{x.kind=kind.value;dirty(d);});label.addEventListener("input",()=>{x.label=label.value;dirty(d);});sha.addEventListener("input",()=>{x.sha256=sha.value;dirty(d);});
      const rm=btn("Remove",()=>{d.references.splice(i,1);dirty(d);showRefs();refStatus.textContent=`Reference ${i+1} removed.`;(refRows.querySelector("select")||addRefBtn).focus();},"btn-small btn-ghost");
      rm.setAttribute("aria-label",`Remove reference ${i+1}`);
      return el("fieldset",{class:"edit-group"},el("legend",{text:`Reference ${i+1}`}),el("div",{class:"edit-grid"},field("Kind",kind),
        field("Label",label,"A filename, log name or short description you keep privately (up to 200 characters)."),
        field("SHA-256 (optional)",sha,"64 hexadecimal characters of the file you keep. The file is not attached or read.")),rm);}));
      addRefBtn.disabled=d.references.length>=maxRefs;refStatus.textContent=d.references.length>=maxRefs?`At most ${maxRefs} references.`:"";}
    showRefs();
    const refsBox=el("fieldset",{class:"edit-group"},el("legend",{text:"Typed references (optional)"}),
      p("Screenshots, logs, saved games or reports that back this observation. Only your label and an optional hash are recorded; nothing is uploaded, attached or opened.","faint"),refRows,addRefBtn,refStatus);
    const syncCategory=()=>{obsBox.hidden=category.value!=="game_user_reported";};
    category.addEventListener("change",()=>{d.values.category=category.value;dirty(d);syncCategory();});syncCategory();
    form.append(field("Category",category,"Game observations are what you saw in Conquest of Elysium 5; they are recorded as user reported."),field("What was observed",summary,"One line, up to 200 characters."),
      field("Details (optional)",det,"Plain text up to 4000 characters: steps, game version, what you checked."),field("Reference (optional)",refIn,"A screenshot filename, log name or similar; files are not attached."),
      refsBox,obsBox,el("button",{type:"submit",class:"btn",text:"Review record"}),box);
    form.addEventListener("submit",e=>{e.preventDefault();box.replaceChildren();
      if(!d.values.summary.trim())return invalid(summary,"Describe what was observed in one line.");
      let observation;
      if(d.values.category==="game_user_reported"){observation={};
        for(const [k] of OBS_LABELS){const v=String(d.observation[k]??"").trim();if(!v)continue;
          if(k==="turns"){if(!/^\d+$/.test(v)||Number(v)>100000)return invalid(obsInputs.turns,"Enter a whole number of turns from 0 to 100000.");observation.turns=Number(v);}
          else if(k==="reference_sha256"){if(!/^[0-9a-fA-F]{64}$/.test(v))return invalid(obsInputs[k],"Enter exactly 64 hexadecimal characters, or leave it empty.");observation[k]=v.toLowerCase();}
          else observation[k]=v;}
        if(!Object.keys(observation).length)observation=undefined;}
      for(const [i,x]of d.references.entries()){const label=String(x.label||"").trim(),sha=String(x.sha256||"").trim();
        if(sha&&!/^[0-9a-fA-F]{64}$/.test(sha))return invalid(form.querySelector(`[name="ref-sha256-${i}"]`),"Enter exactly 64 hexadecimal characters, or leave it empty.");
        if(sha&&!label)return invalid(form.querySelector(`[name="ref-label-${i}"]`),"Describe the file this hash belongs to.");}
      const references=d.references.map(x=>({kind:x.kind,label:String(x.label||"").trim(),sha256:String(x.sha256||"").trim().toLowerCase()}));
      const args={project:m.project.slug,expected_revision:m.revision,category:d.values.category,summary:d.values.summary,details:d.values.details,reference:d.values.reference,
        ...(references.some(x=>x.label||x.sha256)?{references}:{}),...(observation?{observation}:{})};
      reviewWrite(m,d,form,box,"record_evidence",{...args,preview:true},"record_evidence",{...args,preview:false});});
    const obsList=o=>o?el("dl",{class:"kv receipt-facts"},observationRows(o).flatMap(([k,v])=>[el("dt",{text:k}),el("dd",null,v)])):null;
    const rows=r.records.map(x=>[new Date(x.recorded_ns/1e6).toLocaleString(),x.category_label,stack(el("strong",{text:x.summary}),x.details?el("details",null,el("summary",{text:"Details"}),el("pre",{class:"code",text:x.details})):null,x.reference?p(`Reference: ${x.reference}`,"faint"):null,
      x.references?.length?el("dl",{class:"kv receipt-facts"},referenceRows(x.references).flatMap(([k,v])=>[el("dt",{text:k}),el("dd",null,v)])):null,obsList(x.observation)),
      x.current?badge("this revision","ok"):el("span",{class:"faint mono",title:x.revision,text:`older ${short(x.revision)}`})]);
    return stack(p(`Saved revision ${short(m.revision)}. ${r.note}`,"faint"),panel("Record an observation",form),
      panel(`Records (${r.records.length})`,rows.length?table(["Recorded","Category","Observation","Revision"],rows):stateBox("empty","No evidence recorded yet.","Static checks, browser checks, packaging checks and game observations are kept apart.")),
      r.skipped.length?details(`Unreadable records (${r.skipped.length})`,el("ul",null,r.skipped.map(s=>el("li",{text:s})))):null);
  }
  // ---------- export handoff: what to check before giving the ZIP to someone; nothing is installed or published ----------
  function exportHandoff(m){
    const L=m.latest_export,current=L&&L.revision===m.revision,art=artworkSummary(m),drafts=activeDrafts(m.project.slug);
    const rows=[["Static validation passes",m.validation.static_ok,`${m.validation.counts.error} errors · ${m.validation.counts.warning} warnings · ${m.validation.counts.unverified} unverified`],
      ["No unsaved drafts",!drafts.length,drafts.length?`${drafts.length} drafts are not part of the saved revision.`:"Everything shown is saved."],
      ["Latest export matches the saved revision",!!current,L?`${short(L.revision)}${current?"":" is older"}`:"No export yet."],
      ["Artwork checklist reviewed",art.kind==="ok"||art.kind==="info",art.text],
      ["Dependencies named for players",!m.project.dependencies.length||null,m.project.dependencies.length?`Requires: ${m.project.dependencies.join(", ")} (not bundled).`:"No dependencies."],
      ["Evidence recorded separately",null,"Static checks are not game evidence. Record game observations in Evidence before calling a release playable."]];
    return panel("Distribution handoff",p("Hand over the exported ZIP and its manifest. Manifest downloads summarise the catalog without private provenance, paths or snapshot details, including downloads of earlier exports. Earlier copies downloaded before this change may still contain private details; download them again before sharing. Players install the mod folder themselves as described in the official manual. KENOGENESIS does not install into the game, upload to Steam Workshop or publish anything.","faint"),
      el("ul",{class:"ready-list"},rows.map(([label,ok,text])=>el("li",{class:`ready-row is-${ok===null?"info":ok?"ok":"warn"}`},ok===null?el("span",{"aria-hidden":"true"}):badge(ok?"Done":"Check",ok?"ok":"warn"),
        el("span",{class:"ready-label",text:label}),el("span",{class:"ready-text",text:text})))),
      p("The ZIP holds only the .c5m and the files it references or declares. Private catalogs, snapshots, evidence, backups and art-production notes stay in the workspace.","faint"));
  }
  // ---------- CoE5 Workshop staging: a private local ZIP from an existing export; KENOGENESIS never uploads ----------
  function workshopPanel(m){
    const slug=m.project.slug,d=draft(`${slug}:workshop`,{slug,label:"Workshop stage",href:route(m,"export"),values:{export_id:"",visibility:"private",banner:null}});
    const fresh=m.exports.filter(x=>!x.error&&x.revision===m.revision),box=el("div",{"aria-live":"polite"}),history=el("div",null,stateBox("loading","Reading Workshop stages…"));
    const intro=[p("Builds a private local ZIP laid out for the CoE5 Steam Workshop: the chosen export's mod folder plus a square banner.png and coe5ws.txt with your visibility choice. Staging is not an upload.","faint"),
      p("KENOGENESIS never contacts Steam. Any future upload is done by the game itself (Mods, right-click the mod, Upload mod to Steam Workshop) and only with your separate decision.","faint")];
    async function loadHistory(){try{const r=await get(`${base(m)}/workshop`);
      const rows=r.stages.map(x=>[new Date(x.created_ns/1e6).toLocaleString(),x.current?badge("this revision","ok"):el("span",{class:"faint mono",title:x.revision||"",text:`older ${short(x.revision)}`}),x.visibility||"?",
        x.banner?`${x.banner.width}×${x.banner.height} · ${short(x.banner.sha256)}`:"?",x.bundle_status==="ok"?badge("hash matches","ok"):badge(x.bundle_status,"warn"),
        el("div",{class:"btn-row"},x.bundle_status==="ok"?link("Download ZIP",`${base(m)}/workshop/${x.stage_id}/archive`,"btn btn-small"):null,link("Receipt JSON",`${base(m)}/workshop/${x.stage_id}/receipt?download=1`,"btn btn-small btn-ghost"))]);
      history.replaceChildren(rows.length?table(["Staged","Revision","Visibility","Banner","Bundle","Files"],rows):stateBox("empty","No Workshop stages yet."));
      if(r.skipped.length)history.append(details(`Unreadable stage receipts (${r.skipped.length})`,el("ul",null,r.skipped.map(x=>el("li",{text:x})))));}
      catch(e){history.replaceChildren(errorBox(e,loadHistory));}}
    loadHistory();
    const stages=panel("Workshop stages (private)",p("Kept in this project's private .kenogenesis folder, apart from exports. A bundle is offered for download only while it still matches its receipt hash.","faint"),history);
    if(!fresh.length)return stack(panel("Prepare for CoE5 Workshop",intro,stateBox("empty","Export the saved revision first.",
      `Staging reuses an existing export of revision ${short(m.revision)} and checks it byte for byte; it never exports for you. Use Export saved revision above (ZIP or folder), then return here.`)),stages);
    if(!fresh.some(x=>x.export_id===d.values.export_id))d.values.export_id=fresh[0].export_id;
    const form=el("form",{class:"stack"});
    const exp=select("export_id",fresh.map(x=>[x.export_id,`${new Date(x.created_ns/1e6).toLocaleString()} · ${x.format} · ${short(x.revision)}`]),d.values.export_id);exp.addEventListener("change",()=>{d.values.export_id=exp.value;});
    const vis=select("visibility",[["private","Private (default)"],["friends","Friends"],["public","Public"]],d.values.visibility);vis.addEventListener("change",()=>{d.values.visibility=vis.value;});
    const file=input("workshop-banner","","file");file.accept=".png,image/png";const shown=el("div",{class:"sprite-box workshop-banner"});
    function showBanner(){shown.replaceChildren(d.values.banner?stack(el("img",{src:`data:image/png;base64,${d.values.banner.base64}`,alt:`Chosen banner ${d.values.banner.filename}`,width:128,height:128}),p(`${d.values.banner.filename} · ${d.values.banner.bytes} bytes`,"faint mono")):p("No banner chosen.","faint"));}
    file.addEventListener("change",async()=>{const f=file.files[0];box.replaceChildren();if(!f)return;
      if(f.size>4*1024*1024){d.values.banner=null;showBanner();box.replaceChildren(stateBox("error","The banner exceeds the 4 MiB tool limit."));return;}
      d.values.banner=null;showBanner();
      try{const u=await upload(f);d.values.banner={filename:u.filename,base64:u.base64,bytes:f.size};}catch(e){d.values.banner=null;file.value="";box.replaceChildren(errorBox(e));}showBanner();});
    showBanner();
    form.append(field("Reviewed export",exp,"Only exports of the saved revision are offered. Its files are re-read and compared with the saved project."),
      field("Workshop visibility",vis,'Written to coe5ws.txt as Visibility="…". Private is the default.'),
      field("Banner (square PNG)",file,"Copied unchanged as banner.png. The CoE5 modding page suggests 256×256; KENOGENESIS does not resize or redraw it."),shown,
      el("div",{class:"btn-row"},el("button",{type:"submit",class:"btn",text:"Review Workshop stage"})),box);
    const args=()=>({project:slug,expected_revision:m.revision,export_id:d.values.export_id,visibility:d.values.visibility,banner:d.values.banner&&{filename:d.values.banner.filename,base64:d.values.banner.base64}});
    const fail=(e,back)=>{writeFailure(e,m,d,box,back);const c=e.details?.collisions;if(c?.length)box.prepend(table(["Workshop file","Already in the mod payload"],c.map(x=>[x.file,x.existing])));};
    form.addEventListener("submit",async e=>{e.preventDefault();if(d.busy)return;
      if(!d.values.banner){box.replaceChildren(stateBox("error","Choose a square PNG banner first."));file.focus();return;}
      d.busy=true;const controls=[...form.querySelectorAll("input,select,button")].filter(c=>!box.contains(c));controls.forEach(c=>{c.disabled=true;});
      const unlock=()=>controls.forEach(c=>{c.disabled=false;}),back=()=>{box.replaceChildren();unlock();exp.focus();};
      box.replaceChildren(stateBox("loading","Checking the export and preparing the review…"));
      try{const a=args(),r=await post("preview_workshop_stage",a);
        const save=btn("Save new local stage",async()=>{if(d.busy)return;d.busy=true;save.disabled=true;
          try{const s=await post("stage_workshop_bundle",a);toast("Workshop stage saved locally. Nothing was uploaded.");
            box.replaceChildren(panel("Stage saved",stateBox("ok","Saved a new private bundle.","Nothing was uploaded, installed or published. The mod source and revision are unchanged."),
              el("dl",{class:"kv receipt-facts"},el("dt",{text:"Stage"}),el("dd",{class:"mono",text:s.stage_id}),el("dt",{text:"Bundle"}),el("dd",{class:"mono",text:s.file}),
                el("dt",{text:"Bundle SHA-256"}),el("dd",{class:"mono",text:s.bundle_sha256}),el("dt",{text:"Revision"}),el("dd",{class:"mono",text:`${short(s.before_revision)} → ${short(s.revision)} (unchanged)`})),
              el("div",{class:"btn-row"},link("Download ZIP",`${base(m)}/workshop/${s.stage_id}/archive`,"btn"),link("Receipt JSON",`${base(m)}/workshop/${s.stage_id}/receipt?download=1`,"btn btn-ghost"),btn("Stage another",back,"btn-ghost"))));
            loadHistory();box.querySelector("a")?.focus();}
          catch(x){fail(x,back);save.disabled=false;}finally{d.busy=false;}});
        box.replaceChildren(panel("Review Workshop stage",
          el("dl",{class:"kv receipt-facts"},el("dt",{text:"Export"}),el("dd",{class:"mono",text:`${r.export.export_id} (${r.export.format})`}),el("dt",{text:"Revision"}),el("dd",{class:"mono",text:r.revision}),
            el("dt",{text:"coe5ws.txt"}),el("dd",{class:"mono",text:r.coe5ws_txt.trim()}),el("dt",{text:"Banner"}),el("dd",{text:`${r.banner.filename} · ${r.banner.width}×${r.banner.height} · ${r.banner.bytes} bytes`})),
          r.banner.warnings.length?stateBox("warn","Banner size",r.banner.warnings.join(" ")):null,
          table(["File in bundle","Role","Bytes","SHA-256"],r.files.map(f=>[el("span",{class:"mono",text:f.path}),f.role,f.bytes,el("span",{class:"mono",title:f.sha256,text:short(f.sha256)})])),
          el("ul",{class:"art-notes"},r.notes.map(n=>el("li",{text:n}))),
          el("div",{class:"btn-row"},save,btn("Back to the form",back,"btn-ghost"))));
        box.onkeydown=ev=>{if(ev.key==="Escape"&&box.contains(save)){ev.preventDefault();back();}};save.focus();}
      catch(x){unlock();fail(x);}finally{d.busy=false;}});
    return stack(panel("Prepare for CoE5 Workshop",intro,form),stages);
  }
  // ---------- map payloads: listed and hashed; a text header is shown only when the bytes are printable ----------
  async function peekFile(a,out){
    out.replaceChildren(stateBox("loading","Reading file…"));
    try{const r=await getOk(`${a.url}?download=1`);const bytes=new Uint8Array(await r.arrayBuffer()).slice(0,4096);
      const printable=bytes.every(b=>b===9||b===10||b===13||(b>=32&&b<127)||b>=160);
      out.replaceChildren(printable?el("pre",{class:"code",tabindex:"0",text:new TextDecoder("latin1").decode(bytes)}):el("pre",{class:"code mono",text:[...bytes.slice(0,128)].map(b=>b.toString(16).padStart(2,"0")).join(" ")}),
        p(printable?"First 4 KiB as text. KENOGENESIS does not interpret map geometry or validate map content.":"Binary content: first 128 bytes in hex. The map format is not interpreted here.","faint"));}
    catch(e){out.replaceChildren(errorBox(e,()=>peekFile(a,out),`the header of ${a.path}`));}
  }
  // ---------- command-line instructions: the Python serving this page (meta.runtime), quoted for the user's shell ----------
  // Single-quoted literals keep paths with spaces, $, backticks or apostrophes as data. PowerShell doubles an apostrophe;
  // POSIX shells close, escape and reopen the quote. JSON arguments go in a file, which avoids shell quoting of JSON entirely.
  const psQuote=s=>`'${String(s).replace(/'/g,"''")}'`,shQuote=s=>`'${String(s).replace(/'/g,"'\\''")}'`;
  function cliSetup(){
    const rt=state.meta?.runtime?.python_executable?state.meta.runtime:null,win=rt?/^win/i.test(String(rt.platform||"")):/Windows/i.test(navigator.userAgent);
    const q=win?psQuote:shQuote,py=rt?q(rt.python_executable):"<python>",ws=state.meta?.workspace?q(state.meta.workspace):"<workspace>";
    const run=args=>`${win?"& ":""}${py} -m kenogenesis --workspace ${ws} ${args}`;
    const notes=[rt?`Run from the KENOGENESIS folder with the Python serving this browser (${rt.python_executable}, Python ${rt.python_version||"?"}).`:
        "This server did not report its Python: use Python 3.11 or newer (on Windows usually .venv\\Scripts\\python.exe in the KENOGENESIS folder, or py -3) in place of <python>.",
      win?"Shell: PowerShell. & runs the quoted program; '...' is literal text and '' inside it is one apostrophe. Translate the quoting for another shell instead of pasting.":
        "Shell: POSIX (sh, bash or zsh). '...' is literal text and '\\'' inside it is one apostrophe. Translate the quoting for another shell instead of pasting."];
    return {win,q,run,notes};
  }
  // ---------- tools: real local workflows and honest limits ----------
  function toolsView(){
    const reg=state.meta?.registry||[],f={q:"",ctx:""},results=el("div");
    const q=input("cmd-search","","search");q.placeholder="Search commands, e.g. addunitrec or shape";q.setAttribute("aria-label","Search CoE5 commands");
    const contexts=[...new Set(reg.map(e=>e.context).filter(Boolean))].sort(),ctx=select("cmd-context",[["","All contexts"],...contexts.map(c=>[c,kinds[c]?.[1]||c])]);ctx.setAttribute("aria-label","Command context");
    const fill=()=>{const hits=reg.filter(e=>(!f.ctx||e.context===f.ctx)&&`${e.command} ${e.label} ${e.summary||""}`.toLowerCase().includes(f.q.toLowerCase())).slice(0,80);
      results.replaceChildren(p(`${hits.length===80?"First 80":hits.length} commands · CoE5 Modding Manual ${state.meta.manual.version}`,"faint"),
        table(["Command","Context","Signature","Status"],hits.map(e=>[stack(el("strong",{class:"mono",text:e.command}),e.summary?el("div",{class:"faint",text:e.summary}):null),kinds[e.context]?.[1]||e.context||"Not stated",
          e.signature?el("span",{class:"mono",text:`${e.signature}${e.page?` (p.${e.page})`:""}`}):el("span",{class:"faint",text:"Not documented"}),e.status==="curated"?badge("checked","ok"):e.status==="announced"?badge("announced 5.41","warn"):badge("documented","info")])));};
    q.addEventListener("input",()=>{f.q=q.value;fill();});ctx.addEventListener("change",()=>{f.ctx=ctx.value;fill();});fill();
    const projects=state.projects.filter(x=>x.ok);
    return stack(el("h1",{id:"page-title",tabindex:"-1",text:"Tools"}),
      panel("Command reference",p("Checked commands have argument checks in KENOGENESIS; documented commands come from the pinned manual and are preserved verbatim without argument checks. Announced commands are named only in the CoE5 5.41 release notes: no signature is known and they are not checked.","faint"),
        el("div",{class:"btn-row"},q,ctx),results,el("div",{class:"btn-row"},link("Official CoE5 modding manual",state.meta.manual.url),...(state.meta.release_notes||[]).map(r=>link(`${r.title} release notes (${r.date})`,r.url)))),
      panel("Reference catalog import",p("Build a private lookup catalog from local reference .c5m files you are allowed to use. The browser sends file contents; the server never reads a path you type. Catalogs are never exported.","faint"),
        projects.length?el("ul",{class:"plain-list"},projects.map(x=>el("li",null,link(`${x.name||x.slug}: import reference catalog`,path("p",x.slug,"overview","catalog-import"))))):p("Create or import a project first.","faint"),
        link("CATALOG guide",path("docs","CATALOG.md"))),
      panel("Unit artwork conversion",p("Unit frames are 32×32, 64×64 or 128×128 8-bit RGBA PNG or 24/32-bit TGA. Convert generated or drawn art with scripts/prepare-assets.py and a private source manifest, run its read-only --verify, then upload idle and attack together on the unit's sheet.","faint"),
        el("pre",{class:"code",text:"python scripts/prepare-assets.py work/<slug>-art/source-manifest.json\npython scripts/prepare-assets.py work/<slug>-art/source-manifest.json --verify"}),
        p("The converter needs the optional Pillow art dependency; the browser and core do not.","faint"),link("ASSET-RULESET guide",path("docs","ASSET-RULESET.md"))),
      panel("Maps",p("Create maps with CoE5's Map Editor from its Mods menu, then include the .coem using mapfile. Assets lists its size, hash and references and can show a printable header. KENOGENESIS does not edit or interpret map geometry.","faint"),
        link("CoE5 maps and distribution",path("docs","WEB-BROWSER.md")+"?h=maps-and-distribution")),
      (()=>{const cli=cliSetup();
        return panel("Command line and agents",p("Every browser operation is also available as a JSON operation for scripts and coding agents. Put the JSON arguments in a UTF-8 file such as request.json, for example {\"project\":\"my_mod\"}.","faint"),
          el("pre",{class:"code",tabindex:"0",text:[cli.run("run project_model --args-file request.json"),cli.run("commands sndvol --context weapon"),cli.run("mcp")+"   # optional MCP extra"].join("\n")}),
          el("ul",{class:"art-notes"},cli.notes.map(n=>el("li",{text:n}))),
          link("CLI reference",path("docs","CLI_REFERENCE.md")));})(),
      panel("Not provided",el("ul",null,["Installing mods into the game or changing an existing installation","Publishing or Steam Workshop upload","Dominions map, merger, sprite or workshop tools: they target a different game and format",
        "Map editing or .coem generation","Automatic extraction of game data"].map(t=>el("li",{text:t})))));
  }
  function home() {
    return stack(el("h1",{id:"page-title",tabindex:"-1",text:"KENOGENESIS"}),p("A local workshop for Conquest of Elysium 5 mods.","lead"),
      el("div",{class:"grid-2"},panel("Start a mod",p("Create a project, then build classes, units and rituals."),link("Get started",path("start"),"btn")),
        panel("Bring your mod",p("Import a .c5m and the assets you choose. Your original files stay untouched."),link("Import a mod",path("import"),"btn"))),
      panel("Projects",state.projects.length?table(["Project","Target game",""],state.projects.map(x=>[x.ok?link(x.name||x.slug,path("p",x.slug)):el("span",{class:"mono",title:x.error?.message,text:x.slug}),x.target_version||"—",x.ok?"":badge("Unreadable","err")])):
        stateBox("empty","No projects yet.","Create or import a project to begin.")));
  }
  // ---------- original-art agent brief: prepares text only; nothing is generated, uploaded or saved here ----------
  // The agent generates artwork with its own built-in image generation and integrates it through the guarded operations.
  const SLUG_RE=/^[a-z][a-z0-9_]{1,47}$/;
  const ART_READ_FIRST=["AGENTS.md","docs/AGENT_USAGE.md","docs/ASSET-RULESET.md"];
  // Building a faction (create/build) also reads the CoE5 faction-design checklist; artwork-only passes do not need it.
  const readFirst=mode=>mode==="art"?ART_READ_FIRST:[...ART_READ_FIRST,"docs/FACTION-DESIGN.md"];
  const FORM_COMMANDS=new Set(["firstshape","secondshape","growhp","shrinkhp","growtime","growoffs","landshape","watershape","elysiumshape",
    "celestialshape","skyshape","agarthashape","infernoshape","hadesshape","aztlanshape","primalshape","elementalshape","voidshape"]);
  // The theme is brief text, not a project draft: it survives reloads in this tab and never blocks export or navigation.
  const themeKey=slug=>`kenogenesis:art-theme:${slug}`;
  function savedTheme(slug){try{return sessionStorage.getItem(themeKey(slug));}catch(_){return null;}}
  function keepTheme(slug,value){try{sessionStorage.setItem(themeKey(slug),value);}catch(_){/* private mode */}}
  // Brief mode: "create" (no project yet), "build" (project exists but has no class or monster definitions) or "art" (populated faction).
  // Project existence and authoring mode are separate: an existing empty project still needs the faction built in place.
  const isEmptyFaction=m=>!m.objects.some(o=>o.kind==="class"||o.kind==="monster");
  const briefMode=(b,m)=>b.isNew?"create":m&&isEmptyFaction(m)?"build":"art";
  function artInventory(m){
    const frame=s=>s?{path:s.path,line:s.line,status:s.status||"missing",...(s.width?{width:s.width,height:s.height}:{})}:null;
    const monsters=m.objects.filter(o=>o.kind==="monster").map(o=>{const sp=o.view?.sprites||{},inh=sp.inherited;
      return {index:o.index,name:o.display,line:o.line,new:!!o.new,role:o.role,original_art_required:!!o.new,idle:frame(sp.idle),attack:frame(sp.attack),
        inherited_image:inh?{command:inh.command,from:inh.ref,line:inh.line}:null,
        copyspr_lines:o.statements.filter(s=>s.command==="copyspr").map(s=>s.line),
        form_commands:o.statements.filter(s=>FORM_COMMANDS.has(s.command)).map(s=>({command:s.command,args:s.args,line:s.line}))};});
    const images=kind=>m.objects.filter(o=>o.kind===kind&&o.new).map(o=>({index:o.index,name:o.display,line:o.line,image:frame(o.view?.sprite)}));
    const icon=m.mod_info.icon;
    return {revision:m.revision,monsters,new_items:images("item"),new_terrain:images("terrain"),
      mod_banner:icon?{command:"icon",line:icon.line,...frame(m.project.banner)||{path:icon.value,status:"missing"}}:null,
      note:"File status only. Whether an image is original is recorded in the agent's private checklist, not in the project."};
  }
  // Faction design contract (docs/FACTION-DESIGN.md) for create/build briefs only; the text and JSON render this one object.
  // The design record is a private authoring note in the project's docs/ folder, not a product schema; it is never exported.
  function designRequirements(ws,slug){
    return {
      goal:"A complete, original CoE5 class gameplay loop aligned with vanilla structure, not just a small roster with every known summon. No quotas: not every class needs bespoke items, many units or three mage tiers.",
      autonomy:"A theme-only request leaves the design to the agent: make reasonable design decisions without asking for routine approval, and record why.",
      requested_features:"Anything the user explicitly requests is a requirement: implement it with a route and evidence, or report it as missing or blocked. Never mark it complete without it or call it an intentional omission.",
      comparators:"Pick 1-3 relevant vanilla player classes. Label each with its source and version (target game, pinned manual 5.36, or a private catalog with version and provenance); older extracted data is historical, not current engine source. Record strengths, weaknesses and what you adopt or change. Do not copy game text or catalog rows.",
      gameplay_loop:[
        "Identity, intended playstyle and intended weaknesses.",
        "Resource loop: access -> collection or income -> spending -> replenishment; say which parts are built-in game behaviour.",
        "Recruitment: chance, count, gold, gold die, iron and extra costs kept separate; native roster, conditional offers and hired outsiders distinguished.",
        "A valid home citadel and start: start plane, main commander, starting commanders and troops.",
        "Early, middle and late progression that fits the archetype (learning and mastery for casters; upgrades, conversion, conditional recruits, sites or events for others)."],
      magic_and_items:[
        "Combat casting: only through existing combat-magic paths and spells documented in the manual; KENOGENESIS defines no new combat spells.",
        "Rituals: starting knowledge versus learning, caster level and mastery, resource cost and result. Use allrit only as a deliberate knowledge policy with a written reason.",
        "Items: shared loot, starting equipment or own items; slots and acquisition. Shared loot is valid; add bespoke items when the design or the user needs them. A unit's weapon is not an equippable item."],
      reachability:"Every new unit, item, ritual, upgrade and alternate form has an acquisition route with prerequisites and costs. Summons and forms need a reachable summoner or parent; support definitions name their reachable consumer. Explain unused internal support. Trace unlocks from the starting state, including the first resource and ritual, without circular prerequisites or unobtainable costs.",
      commands_and_order:"Use the signature lookup_command returns (manual), not argument forms from old data dumps; label documented commands that are not argument-checked as documented-but-unvalidated. Define in reference order: newritpow before units or rituals that use relative school numbers (power 0, -1), and named monsters, weapons and terrain before lines naming them; alternate-form references follow new-monster order (manual p.18).",
      design_record:{path:`${ws.replace(/\\/g,"/").replace(/\/$/,"")}/${slug}/docs/design.md`,
        when:"Write it before the first guarded source edit (in create mode, after create_project) and keep it current.",
        nature:"Private authoring note: KENOGENESIS lists and reads it but never edits or exports it. Not a product file or schema.",
        contents:["comparators with versions","identity, playstyle and weaknesses","resource loop","recruitment and starting forces","early, middle and late progression","combat casting, rituals and items decisions","coverage table"],
        coverage_columns:["requested or chosen feature","authored definition","acquisition route and prerequisites","progression and resource costs","artwork","evidence: static / browser / package / game","status"],
        statuses:{implemented:"authored, reachable through its route, statically valid and with artwork done; game behaviour nobody has observed stays 'unverified in game'",
          "omitted (optional)":"not requested; reason written down","blocked or unverified":"depends on unsupported, documented-only or untested behaviour; say what blocks it",
          missing:"not done; a requested feature stays missing until implemented"}},
      evidence:"Static, browser and package checks do not show that the faction is playable, balanced or engine verified. Game cases (start, resource income, recruitment, ritual learning, cost and result, item, upgrade and form acquisition, combat, save and reload; docs/VALIDATION.md) stay deferred unless the user asks for game testing.",
      sources:["https://www.illwinter.com/coe5/coe5manual.html","https://www.illwinter.com/coe5/coe5modding.html"]};
  }
  function designContractLines(d){
    const r=d.design_record;
    return ["Design contract (docs/FACTION-DESIGN.md):",`- Goal: ${d.goal}`,`- ${d.autonomy}`,`- ${d.requested_features}`,`- Comparators: ${d.comparators}`,
      "- Gameplay loop:",...d.gameplay_loop.map(x=>`  - ${x}`),"- Magic and items, as separate decisions:",...d.magic_and_items.map(x=>`  - ${x}`),
      `- Reachability: ${d.reachability}`,`- Commands and order: ${d.commands_and_order}`,
      `- Private design record: ${r.path}. ${r.when} ${r.nature} Contents: ${r.contents.join("; ")}.`,
      `  Coverage columns: ${r.coverage_columns.join(" | ")}.`,
      "  Status values:",...Object.entries(r.statuses).map(([k,v])=>`  - ${k}: ${v}.`),
      `- Evidence: ${d.evidence}`,`- Primary sources: ${d.sources.join(" and ")}`];
  }
  function artBriefText(b,inv){
    const ws=state.meta?.workspace||"<workspace>",slug=b.slug,isNew=b.isNew,mode=b.mode||(isNew?"create":"art");
    const img=(f,label)=>f?`${label} ${f.path} (${f.status}${f.width?`, ${f.width}x${f.height}`:""})`:null;
    const unitLine=u=>`- ${u.name} [#${u.index}, line ${u.line}] ${u.role}: `+[img(u.idle,"idle")||"idle not set",
      img(u.attack,"attack")||(u.idle?"attack not set (spr1 used for both)":"attack not set"),
      u.inherited_image?`image inherited via ${u.inherited_image.command} "${u.inherited_image.from}" (placeholder)`:null,
      u.copyspr_lines.length?`copyspr on line ${u.copyspr_lines.join(", ")}`:null,
      u.form_commands.length?`form commands: ${u.form_commands.map(f=>`${f.command} ${f.args.join(" ")}`.trim()).join(", ")}`:null].filter(Boolean).join("; ");
    const roster=inv?(()=>{const req=inv.monsters.filter(u=>u.original_art_required),sel=inv.monsters.filter(u=>!u.original_art_required);
      return [`Roster and forms at revision ${inv.revision} (file status only; record originality in your checklist):`,
        ...(req.length?req.map(unitLine):["- No new monsters yet."]),
        sel.length?`Selected vanilla monsters (no new art unless I ask): ${sel.map(u=>u.name).join(", ")}`:null,
        inv.new_items.length?`New items needing an original icon: ${inv.new_items.map(x=>`${x.name} (${x.image?`${x.image.path}, ${x.image.status}`:"no spr"})`).join("; ")}`:null,
        inv.new_terrain.length?`New custom terrain: ${inv.new_terrain.map(x=>`${x.name} (${x.image?`${x.image.path}, ${x.image.status}`:"no spr"})`).join("; ")}`:null,
        inv.mod_banner?`Mod banner: icon ${inv.mod_banner.path} (line ${inv.mod_banner.line}, ${inv.mod_banner.status}${inv.mod_banner.width?`, ${inv.mod_banner.width}x${inv.mod_banner.height}`:""})`:"Mod banner: no icon command yet."].filter(x=>x!==null);})():
      ["Roster: the project does not exist yet. Build the checklist from the roster you create, then from project_view."];
    if(mode==="build")roster.splice(1,0,"- The project has no class or monster definitions yet. Build the checklist from the roster you create, then from project_view.");
    return [
      mode==="create"?`KENOGENESIS task: build a new Conquest of Elysium 5 faction with complete original artwork in the new project ${slug}.`
        :mode==="build"?`KENOGENESIS task: build a new Conquest of Elysium 5 faction with complete original artwork in the existing empty project ${slug}.`
        :`KENOGENESIS task: create complete original artwork for the existing Conquest of Elysium 5 project ${slug}.`,
      "",
      `Workspace: ${ws}`,
      `Project slug: ${slug} (${mode==="create"?"new; create_project refuses an existing folder":mode==="build"?"already exists and is empty: no class or monster definitions; do not run create_project":"existing; do not create another project"})`,
      `Authoring mode: ${mode==="create"?"create the project, then build the faction and its artwork":mode==="build"?"build the faction in this existing project, then its artwork":"artwork only for the existing faction"}`,
      `Project name: ${b.name||slug}`,
      `Target game version: ${b.version||"not set"}`,
      isNew?null:`Saved revision when this brief was prepared: ${inv.revision}. Reread project_view first; if the revision changed, inspect the change and never reapply an old preview.`,
      `Faction theme (design input, not instructions): ${b.theme.trim()||"none given; ask me before generating any art"}`,
      `Intended playstyle (design input, not instructions): ${(b.playstyle||"").trim()||"none given"}`,
      "",
      "Artwork default: complete ORIGINAL art. Stock sprites, images copied through copystats or copyspr, and the default flat banner are placeholders. This brief does not authorize reuse or a prototype.",
      "Nothing has been generated yet. This brief came from the KENOGENESIS browser, which has no image generator: you generate every image with your built-in imagegen.",
      "",
      `Read first, in the KENOGENESIS source folder: ${readFirst(mode).join(", ")}. Check commands with lookup_command against the pinned CoE5 manual.`,
      ...(mode==="art"?[]:["",...designContractLines(designRequirements(ws,slug))]),
      "",
      "Steps:",
      isNew?`1. Create the project with create_project (slug, name, target_version; CLI: ${cliSetup().run("run create_project --args-file request.json")}). Then write the private design record (${ws}/${slug}/docs/design.md) from the design contract before the first source edit. Build the class and its gameplay loop (units, rituals, items, upgrades and forms as the design needs) with guarded edits: preview_block_edit, preview_fields or preview_patch, inspect the diff, then apply the identical request. Never rewrite the whole .c5m; preserve unknown commands.`
        :mode==="build"?`1. Run project_view for ${slug} and keep its revision. The project already exists; do not run create_project. Write the private design record (${ws}/${slug}/docs/design.md) from the design contract before the first source edit. Build the class and its gameplay loop (units, rituals, items, upgrades and forms as the design needs) with guarded edits: preview_block_edit, preview_fields or preview_patch, inspect the diff, then apply the identical request. Never rewrite the whole .c5m; preserve unknown commands. Use the new revision after every save.`
        :`1. Run project_view for ${slug} and keep its revision. Change artwork references only; leave gameplay values unchanged in this pass.`,
      `2. Write a private asset checklist under work/${slug}-art/ (ignored; never inside mod/ or the export): idle and attack paths for every new troop, commander, summon and alternate form (resolve shapechanging targets from source order, manual p.18); the mod banner (icon, 256x64); an icon for each new item; an image for each new custom terrain. CoE5 has no flag or spell icon command; do not add them.`,
      "3. Generate each monster's idle and attack poses in one imagegen call. Keep exact prompts, raw outputs, hashes and conversion records in that private folder.",
      `4. Use scripts/prepare-assets.py with a measured private source-manifest.json under work/${slug}-art/ (see ASSET-RULESET.md), then run its read-only --verify. It uses a shared body scale per pair and refuses to shrink a unit to fit a raised weapon. Convert to a 32x32 or 64x64 canvas (128x128 only for huge monsters), a human about 34 px tall with 2 free pixels under the feet; no background. PNG alpha is binary by authoring policy; honour the documented black/magenta key for opaque TGA. Do not repaint during conversion. preview_art_upload refuses other unit canvases, unsupported PNG types (use 8-bit RGBA, non-interlaced, or 24/32-bit TGA), corrupt files, empty frames and partly transparent stored alpha (authoring policy, not a documented engine rule). It reports foot rows, edge contact, huge-canvas and pair consistency warnings.`,
      `5. Integrate each monster in ONE guarded review: preview_art_upload with object_index and frames [{"frame":"spr1","asset_path":<new path>,"content":<base64>},{"frame":"spr2",...}]; inspect each frame's facts and warnings, the change list and the diff; then apply_art_upload with the identical request. One save writes both new files and the source change or nothing; it removes copyspr from that monster and places spr1 then spr2 after its last copystats. The banner, item and terrain images have no upload operation: write each to a NEW filename in mod/${slug}/, then change its reference with preview_block_edit and apply_block_edit (object_index -1 for icon); they get container and size checks only. Never overwrite or delete an existing file. Use the new revision after every save.`,
      "6. Keep built-in sounds; add custom samples only if I ask.",
      ...(()=>{const cli=cliSetup();return [`CLI fallback when the KENOGENESIS MCP tools are not connected: ${cli.run("run <operation> --args-file request.json")}`,...cli.notes];})(),
      `7. Audit both poses at native size and enlarged (nearest-neighbour), plus the Overview Artwork checklist in the browser (placeholders, idle-only units, shared files, banner, items, terrain); run validate_mod (no missing assets, spr2 after spr1). ${mode==="art"?"Export with export_mod for the reviewed revision":"When export is in scope, use export_mod for the reviewed revision"} and check that the manifest lists every image and no private provenance.`,
      `8. Report the checklist status, missing or blocked assets by name, and the checks you ran. If generation is blocked, stop and name the unfinished assets; never substitute stock art silently. File checks are not in-game proof; ${mode==="art"?"do not install anything into the game.":"follow the user's scope for export, installation and game testing; never install, launch or publish unless already authorized."}`,
      mode==="art"?null:"9. Before reporting, audit reachability against the design record and report every coverage row with its status. Requested features that are not done stay missing or blocked; list game cases as deferred unless I asked for game testing.",
      "",
      ...roster,
      "",
      `I will review the result at ${location.origin}/${path("p",slug)} after pressing Reload.`,
    ].filter(x=>x!==null).join("\n");
  }
  function artBriefJson(b,inv,text){
    const mode=b.mode||(b.isNew?"create":"art");
    return {schema:"kenogenesis.art-brief/1",kind:"original-art",
      note:"Agent brief only. Preparing it generated, uploaded and saved nothing. The agent generates artwork with its built-in imagegen and integrates it through KENOGENESIS's guarded operations.",
      workspace:state.meta?.workspace||null,
      project:{slug:b.slug,name:b.name||b.slug,target_version:b.version||null,new:b.isNew,exists:!b.isNew,
        empty:mode==="create"?null:mode==="build",revision:inv?.revision||null},
      authoring_mode:mode,
      authoring:{create:{create_project:true,build_faction:true,artwork:true},build:{create_project:false,build_faction:true,artwork:true},
        art:{create_project:false,build_faction:false,artwork:true}}[mode],
      faction_theme:b.theme.trim(),playstyle:(b.playstyle||"").trim()||null,
      art_default:{original:true,reuse_or_prototype_authorized:false,
        required:["idle (spr1) and attack (spr2) for every new troop, commander, summon and alternate form","original thematic mod banner (icon, 256x64)",
          "original icon (spr) for every new magic item","original image (spr) for every new custom terrain"],
        not_applicable:["nation flags","spell or ritual icons"],placeholders:"Stock, copystats/copyspr and default images are placeholders until replaced.",
        sound:"Built-in sounds by default; custom samples only on request.",generation:"Agent built-in imagegen; KENOGENESIS has no image generator."},
      read_first:readFirst(mode),
      ...(mode==="art"?{}:{design_requirements:designRequirements(state.meta?.workspace||"<workspace>",b.slug)}),
      guarded_workflow:["project_view: keep the revision","preview_* then apply_* with the identical request","reread project_view after a stale_revision; never reapply an old preview",
        "validate_mod",mode==="art"?"export_mod for the reviewed revision; inspect the manifest":"when export is in scope: export_mod for the reviewed revision; inspect the manifest"],
      asset_rules:["unit conversion: scripts/prepare-assets.py with a private measured source manifest, then --verify; one body scale per pair, no shrink-to-fit","unit frames: one preview_art_upload with frames [spr1, spr2] then apply_art_upload with the identical request; new paths only; the save writes both files and the source change together or nothing","the paired save removes copyspr and places spr1 then spr2 after the last copystats; no separate copyspr edit is needed","unit frames: 32x32, 64x64 or 128x128 (huge only); empty frames and partial stored alpha are refused as authoring policy; opaque TGA retains its black/magenta colour key",
        "banner, item and terrain images have no upload operation: write a new filename in the mod folder, then change the reference with preview_block_edit/apply_block_edit (object_index -1 for icon)",
        "never overwrite or delete existing files","prompts, raw outputs, conversion records and the checklist stay private under work/ and out of the export"],
      inventory:inv||null,agent_instructions:text};
  }
  // Clipboard access can be refused (permissions, insecure context); callers show the outcome persistently.
  async function copyText(text){
    try{if(!navigator.clipboard)throw new Error("unavailable");await navigator.clipboard.writeText(text);return true;}catch(_){return false;}
  }
  function downloadJson(name,data){
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));
    const a=el("a",{href:url,download:name,hidden:true});document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  // b() returns {slug,name,version,isNew,mode,theme,playstyle}; m is the saved model for an existing project.
  // opts: setPlaystyle(value); progress: an object that remembers the hand-off (Get started shows prepare → hand off → return).
  function artBriefPanel(b,m,setTheme,themeHelp,opts={}){
    const inv=m?artInventory(m):null,current=()=>b(),track=opts.progress||null;
    const theme=area("faction-theme",current().theme,3);theme.id="art-theme";theme.spellcheck=true;
    const play=area("faction-playstyle",current().playstyle||"",2);play.id="art-playstyle";play.spellcheck=true;
    const status=el("p",{class:"field-meta faint",role:"status"}),preview=el("pre",{class:"code brief-text",tabindex:"0","aria-label":"Agent brief text"});
    // Copy and download outcomes stay on screen; a refused clipboard reveals selectable text to copy by hand.
    const outcome=el("div",{role:"status","aria-live":"polite"}),manual=el("div");
    const stamp=()=>new Date().toLocaleTimeString();
    // Every brief input is part of what was handed over; changing any of them makes the earlier copy out of date.
    const sig=c=>JSON.stringify([c.slug||"",c.name||"",c.version||"",(c.theme||"").trim(),(c.playstyle||"").trim()]);
    let delivered=track?.handoff?.sig??null;
    const handed=how=>{delivered=sig(current());if(track){track.handoff={slug:current().slug,how,time:stamp(),sig:delivered};showSteps();}};
    const copy=btn("Copy brief text",async()=>{const c=current(),text=artBriefText(c,inv);manual.replaceChildren();
      if(await copyText(text)){outcome.replaceChildren(stateBox("ok",`Brief copied at ${stamp()}.`,"Paste it into Codex or Claude Code opened on the KENOGENESIS folder."));handed("copied");return;}
      const box=el("textarea",{class:"input code",rows:"10",readonly:true,spellcheck:"false","aria-label":"Agent brief text to copy manually",text});
      outcome.replaceChildren(stateBox("error","Copy failed: the browser did not allow clipboard access.","The brief is selected below. Copy it with Ctrl+C (or ⌘C), then confirm."));
      manual.replaceChildren(box,el("div",{class:"btn-row"},btn("I copied it manually",()=>{manual.replaceChildren();outcome.replaceChildren(stateBox("ok",`Brief copied manually at ${stamp()}.`));handed("copied manually");},"btn-small"),
        btn("Download brief JSON instead",()=>download.click(),"btn-small btn-ghost")));
      box.focus();box.select();});
    const download=btn("Download brief JSON",()=>{
      const c=current(),text=artBriefText(c,inv),name=`${c.slug}-original-art-brief.json`;downloadJson(name,artBriefJson(c,inv,text));
      outcome.replaceChildren(stateBox("ok",`Downloaded ${name} at ${stamp()}.`,"Give the file to your agent; it holds the same instructions as the text."));handed("downloaded");},"btn-ghost");
    // Get started progress: nothing here creates a project; the return step only reloads the list and looks for the exact slug.
    const steps=el("ol",{class:"create-steps","aria-label":"Brief progress"}),back=el("div"),found=el("div",{role:"status","aria-live":"polite"});
    function showSteps(){if(!track)return;const c=current(),h=track.handoff&&track.handoff.sig===sig(c),ok=SLUG_RE.test(c.slug||"")&&!state.projects.some(x=>x.slug===c.slug);
      const at=h?2:ok?0:-1;
      steps.replaceChildren(...["Prepare the brief","Hand it to your agent","Return and open the project"].map((t,i)=>el("li",{class:i<at||(i===1&&h)?"is-done":i===at?"is-current":null,"aria-current":i===at?"step":null},
        el("span",{class:"step-n","aria-hidden":"true",text:String(i+1)}),t)));
      back.replaceChildren(h?stack(p(`Handed off (${track.handoff.how}) at ${track.handoff.time}. When the agent reports that ${c.slug} exists, check for it here. KENOGENESIS never creates it from the brief.`,"faint"),
        btn(`Reload projects and check for ${c.slug}`,async e=>{const b2=e.currentTarget;b2.disabled=true;found.replaceChildren(stateBox("loading","Reloading projects…"));
          try{await reloadProjects();const x=state.projects.find(y=>y.slug===c.slug);refresh();
            found.replaceChildren(!x?stateBox("empty",`No project named ${c.slug} yet.`,"The agent creates it with create_project; check again when it reports back."):
              !x.ok?stateBox("error",`${c.slug} exists but cannot be read.`,x.error?.message||""):
              stack(stateBox("ok",`Found ${x.name||c.slug} (${c.slug}).`),link(`Open ${x.name||c.slug}`,path("p",c.slug,"overview","art-brief"),"btn btn-small")));}
          catch(x){found.replaceChildren(errorBox(x));}finally{b2.disabled=false;}},"btn-small"),found):"");}
    function refresh(){const c=current(),ok=SLUG_RE.test(c.slug||""),exists=c.isNew&&state.projects.some(x=>x.slug===c.slug);
      if(delivered!==null&&sig(c)!==delivered){delivered=null;if(track)track.handoff=null;manual.replaceChildren();
        outcome.replaceChildren(stateBox("warn","The brief changed after it was copied or downloaded.","The earlier copy is out of date. Copy or download it again so your agent receives the current text."));}
      copy.disabled=download.disabled=!ok||exists;
      if(exists)status.replaceChildren("A project with this folder name already exists. Its brief is on its ",link("Overview",path("p",c.slug,"overview","art-brief")),".");
      else status.textContent=!ok?"Enter a valid project folder name to prepare the brief.":"";
      preview.textContent=ok&&!exists?artBriefText(c,inv):"";showSteps();}
    theme.addEventListener("input",()=>{setTheme(theme.value);refresh();});
    play.addEventListener("input",()=>{opts.setPlaystyle?.(play.value);refresh();});
    const req=inv?.monsters.filter(u=>u.original_art_required)||[];
    const summary=inv&&current().mode==="build"?p("This project exists but has no class or monster definitions yet. The brief asks the agent to build the faction in this project, then generate its complete original artwork."):inv?p(`${req.length} new monster${req.length===1?"":"s"} need original idle and attack images · ${inv.new_items.length} new item${inv.new_items.length===1?"":"s"} · ${inv.new_terrain.length} custom terrain · mod banner ${inv.mod_banner?inv.mod_banner.path:"not set"}. File status is listed in the brief; originality is tracked by the agent.`):null;
    refresh();
    return {refresh,node:stack(
      track?steps:null,
      p("New factions get complete original artwork by default: idle and attack images for every new troop, commander, summon and alternate form, an original mod banner, and item or terrain images where the content needs them. Stock or copied images are placeholders unless you explicitly ask for reuse or a prototype."),
      summary,field("Faction theme",theme,themeHelp),
      field("Intended playstyle (optional)",play,"How the faction should feel to play, such as fast raiders or slow ritual builders. Passed to the agent as design input; no balance is computed."),
      el("div",{class:"btn-row"},copy,download),status,outcome,manual,
      p("There is no image model in this browser. These buttons only copy or download text: nothing is generated, uploaded or saved, no project is created, and existing source and artwork stay unchanged. Paste the brief into Codex or Claude Code opened on the KENOGENESIS folder: the agent generates the images with its built-in image generation and saves them through the guarded review.","panel-note"),
      track?back:null,
      details("Preview brief text",preview),
      el("p",{class:"faint"},"Rules: ",link("ASSET-RULESET",path("docs","ASSET-RULESET.md"))," · ",link("AGENT_USAGE",path("docs","AGENT_USAGE.md"))))};
  }
  const playKey=slug=>`kenogenesis:art-playstyle:${slug}`;
  function projectArtBrief(m,open){
    const slug=m.project.slug,derived=m.project.name||slug;
    let value=savedTheme(slug)??derived,playstyle=storeGet("sessionStorage",playKey(slug))||"";
    const mode=briefMode({isNew:false},m);
    const b=()=>({slug,name:m.project.name,version:m.project.target_version,isNew:false,mode,theme:value,playstyle});
    const {node}=artBriefPanel(b,m,v=>{value=v;keepTheme(slug,v);},"Prefilled from the project name. Edit freely; it is passed to the agent as design input.",
      {setPlaystyle:v=>{playstyle=v;storeSet("sessionStorage",playKey(slug),v);}});
    const title="Original artwork: agent brief";
    if(open)return el("section",{class:"panel",id:"art-brief","aria-labelledby":"art-brief-h"},el("h3",{id:"art-brief-h",text:title}),node);
    return el("details",{class:"tech",id:"art-brief"},el("summary",{text:title}),node);
  }
  // Get started inputs survive a reload of this tab (sessionStorage). A restored value is used only when the stored
  // shape is exactly the expected bounded strings; denied or corrupt storage simply starts with an empty form.
  const START_KEY="kenogenesis:start-form",START_LIMITS={slug:120,name:200,version:40,theme:4000,playstyle:4000};
  function restoredStart(){
    let v;try{v=JSON.parse(storeGet("sessionStorage",START_KEY)||"null");}catch(_){v=undefined;}
    const fail=()=>{if(v!==null)storeSet("sessionStorage",START_KEY,null);return null;};
    if(!v||typeof v!=="object"||Array.isArray(v)||!v.values||typeof v.values!=="object"||Array.isArray(v.values))return fail();
    const values={};
    for(const [k,n]of Object.entries(START_LIMITS)){const x=v.values[k]??"";if(typeof x!=="string"||x.length>n)return fail();values[k]=x;}
    return {values,themeTouched:v.themeTouched===true};
  }
  const saveStart=d=>storeSet("sessionStorage",START_KEY,JSON.stringify({values:d.values,themeTouched:!!d.themeTouched}));
  function startView() {
    if(!state.drafts.has("create-project")){const r=restoredStart();
      const d0=draft("create-project",{slug:null,label:"Create project",href:path("start"),values:r?.values||{slug:"",name:"",version:"",theme:"",playstyle:""},themeTouched:!!r?.themeTouched});
      if(r&&Object.values(r.values).some(Boolean))d0.dirty=true;}
    const d=draft("create-project",{});
    if(d.values.theme===undefined)d.values.theme="";
    if(d.values.playstyle===undefined)d.values.playstyle="";
    const form=el("form",{class:"stack"}),box=el("div");
    const derived=()=>d.values.name.trim()||d.values.slug;
    // The hand-off record lives with this tab's Get started state; it is not a draft change and creates nothing.
    const progress=state.filters.get("start:brief")||{};state.filters.set("start:brief",progress);
    const brief=artBriefPanel(()=>({slug:d.values.slug.trim(),name:d.values.name.trim(),version:d.values.version.trim(),isNew:true,mode:"create",
      theme:d.themeTouched?d.values.theme:derived(),playstyle:d.values.playstyle}),null,
      v=>{d.values.theme=v;d.themeTouched=true;dirty(d);saveStart(d);},"Prefilled from the display name. Edit freely; it is passed to the agent as design input. Creating an empty project does not use it.",
      {setPlaystyle:v=>{d.values.playstyle=v;dirty(d);saveStart(d);},progress});
    const themeInput=$("#art-theme",brief.node),inputs={};
    for(const [key,label]of [["slug","Project folder name"],["name","Display name"],["version","Target game version"]]){const c=input(key,d.values[key]);inputs[key]=c;
      if(key==="slug"){c.required=true;c.pattern="[a-z][a-z0-9_]{1,47}";}
      c.addEventListener("input",()=>{d.values[key]=c.value;dirty(d);saveStart(d);box.replaceChildren();if(!d.themeTouched)themeInput.value=derived();brief.refresh();});form.append(field(label,c));}
    const clearForm=btn("Clear form",()=>{storeSet("sessionStorage",START_KEY,null);state.drafts.delete(d.key);progress.handoff=null;render();},"btn-ghost");
    form.append(el("div",{class:"btn-row"},el("button",{type:"submit",class:"btn",text:"Create empty project"}),clearForm),box);
    form.addEventListener("submit",async e=>{e.preventDefault();if(d.busy)return;const slug=d.values.slug.trim();
      if(!SLUG_RE.test(slug)){invalid(inputs.slug,"Use 2–48 lowercase letters, digits or underscores, starting with a letter.");return;}
      if(state.projects.some(x=>x.slug===slug)){invalid(inputs.slug,"A project with this folder name already exists. Choose another name; nothing is overwritten.");return;}
      d.busy=true;try{await post("create_project",{slug,name:d.values.name||null,target_version:d.values.version||null});
      if(d.themeTouched)keepTheme(slug,d.values.theme);
      if(d.values.playstyle)storeSet("sessionStorage",playKey(slug),d.values.playstyle);
      storeSet("sessionStorage",START_KEY,null);state.drafts.delete(d.key);await reloadProjects();toast("Project created. Its original-art agent brief is open on the Overview.");location.hash=path("p",slug,"overview","art-brief");}
      catch(x){box.replaceChildren(errorBox(x));const c=x.code==="dest_exists"||x.code==="bad_project"?inputs.slug:null;if(c)invalid(c,x.message);}finally{d.busy=false;}});
    return stack(el("h1",{id:"page-title",tabindex:"-1",text:"Get started"}),el("ol",{class:"steps"},["Create or import","Build and review","Validate and export"].map((x,i)=>el("li",{"aria-current":i===0?"step":null,text:x}))),
      panel("Plan the faction",p("A Conquest of Elysium 5 faction is a class with a complete gameplay loop, not a quota of units or summons. Plan these together before building:","faint"),
        el("ol",null,["Identity: what makes it play differently, its playstyle and its intended weaknesses, compared with 1–3 vanilla classes",
          "Economy: where its resources come from, how they are spent and replenished; recruitment chances, counts, gold and iron",
          "Home: a real home citadel terrain, start plane, main commander and starting army","Progression: what changes in the early, middle and late game",
          "Magic and items: combat casting, ritual learning and costs, and item acquisition, decided separately","Alternate forms, plane or terrain roles and events, if the theme needs them",
          "A route to every new unit, item, ritual and form, and original artwork for each new unit and form, and a banner"].map(t=>el("li",{text:t}))),
        el("p",{class:"faint"},"The create and build agent briefs carry this as a design contract, including a private design and coverage record. Guide: ",link("FACTION-DESIGN",path("docs","FACTION-DESIGN.md")),". Static checks do not show that a faction is playable or balanced; test in the game.")),
      panel("Create a project",p("Creates an empty project with a flat placeholder banner. Nothing else is written.","faint"),form),
      panel("Original artwork: agent brief",brief.node));
  }
  async function upload(file) {
    const bytes=new Uint8Array(await file.arrayBuffer());let text="";for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));
    return {filename:file.name,path:file.webkitRelativePath||file.name,base64:btoa(text)};
  }
  // Browser-side preflight mirrors the server's tool policy (core.py); the server still repeats every check.
  const MIB=1024*1024,IMPORT_TOTAL=8*MIB,IMPORT_FILE=16*MIB,IMPORT_ASSETS=200,ART_MAX=2*MIB;
  const SAFE_PART=/^[A-Za-z0-9_][A-Za-z0-9_.-]*$/;
  // paths.mod_relpath_problems: relative, forward slashes, no traversal, conservative portable names.
  function assetPathProblem(v){
    if(!v)return "Enter a relative path.";if(v.includes("\\"))return "Use forward slashes (/), as the manual requires.";
    if(v.startsWith("/")||/^[A-Za-z]:/.test(v))return "Use a path relative to the mod folder.";
    const parts=v.split("/").filter(x=>x&&x!==".");if(parts.includes(".."))return "Paths cannot contain '..'.";
    const bad=parts.find(x=>!SAFE_PART.test(x));return bad?`"${bad}" contains spaces or special characters.`:null;
  }
  function importView() {
    const d=draft("import",{slug:null,label:"Import a mod",href:path("import"),values:{slug:"",name:"",version:""},source:null,assets:[]});
    const form=el("form",{class:"stack"}),box=el("div",{"aria-live":"polite"});
    // The outcome of a completed import stays on this page until the user opens the project or starts another import.
    if(d.done)return stack(el("h1",{id:"page-title",tabindex:"-1",text:"Import a mod"}),panel("Import complete",
      stateBox("ok",`Imported ${d.done.name} (${d.done.slug}).`,"A new project was created from the reviewed files. Static checks follow in its Validation section."),
      table(["Property","Value"],[["Project",d.done.slug],["Revision",d.done.revision],["Source SHA-256",d.done.sha256],["Files",String(d.done.files)]]),
      el("div",{class:"btn-row"},link(`Open ${d.done.name}`,path("p",d.done.slug),"btn"),btn("Import another mod",()=>{state.drafts.delete(d.key);render();},"btn-ghost"))));
    const controlsByKey={};
    const clear=()=>{if(!d.busy)box.replaceChildren();};
    for(const [key,label,help]of [["slug","New project folder name","2–48 lowercase letters, digits or underscores, starting with a letter. The .c5m is saved as <name>.c5m."],
      ["name","Display name",null],["version","Target game version",null]]){
      const c=input(key,d.values[key]);controlsByKey[key]=c;if(key==="slug"){c.required=true;c.pattern="[a-z][a-z0-9_]{1,47}";}
      c.addEventListener("input",()=>{d.values[key]=c.value;dirty(d);clear();});form.append(field(label,c,help));}
    const sourceStatus=el("div",{class:"field-meta faint",role:"status"});
    const showSource=()=>{sourceStatus.textContent=d.sourceReading?"Reading the source file…":d.source?`Selected: ${d.source.filename} (${d.source.bytes??"?"} bytes)`:d.sourceError||"No source chosen.";};
    const source=input("source","","file");source.accept=".c5m";
    // A new choice replaces the earlier source only after it has been read; a failed read leaves no source selected.
    source.addEventListener("change",async()=>{const x=source.files[0];if(!x)return;const mine=d.sourceTicket=(d.sourceTicket||0)+1;d.sourceReading=true;
      d.source=null;d.sourceError=null;clear();showSource();
      try{if(!/\.c5m$/i.test(x.name))throw new Error("The mod file must end in .c5m.");
        if(x.size>IMPORT_FILE)throw new Error("The source exceeds the 16 MiB tool limit.");
        if(x.size+d.assets.reduce((n,a)=>n+(a.bytes||0),0)>IMPORT_TOTAL)throw new Error("The source and assets are limited to 8 MiB in total (tool policy).");
        const u=await upload(x);if(mine!==d.sourceTicket)return;d.source={...u,bytes:x.size};dirty(d);}
      catch(e){if(mine!==d.sourceTicket)return;d.sourceError=`${x.name} was not read: ${e.message||"the file could not be read"}`;source.value="";markInvalid(source,d.sourceError);}
      finally{if(mine===d.sourceTicket)d.sourceReading=false;showSource();}});
    showSource();
    const assetPaths=el("div",{class:"stack"}),assetStatus=el("div",{class:"field-meta faint",role:"status"});
    function showAssets(){assetStatus.textContent=d.assetsReading?"Reading asset files…":d.assets.length?`${d.assets.length} asset file${d.assets.length===1?"":"s"} · ${d.assets.reduce((n,a)=>n+(a.bytes||0),0)} bytes`:d.assetsError||"No assets chosen.";
      assetPaths.replaceChildren(...d.assets.map((a,i)=>{const c=input(`asset-path-${i}`,a.path);c.addEventListener("input",()=>{a.path=c.value;dirty(d);clear();});
      const rm=btn("Remove",()=>{d.assets=d.assets.filter(x=>x!==a);dirty(d);clear();showAssets();},"btn-ghost btn-small");rm.setAttribute("aria-label",`Remove ${a.filename}`);
      return el("div",{class:"btn-row"},field(a.filename,c),rm);}));}
    async function chooseAssets(files,folder=false){const mine=d.assetsTicket=(d.assetsTicket||0)+1;d.assetsReading=true;d.assets=[];d.assetsError=null;d.assets=[];clear();
      try{const sourceBytes=d.source?.bytes||0,total=files.reduce((n,f)=>n+f.size,0);
        if(files.length>IMPORT_ASSETS)throw new Error(`Choose at most ${IMPORT_ASSETS} asset files.`);
        if(files.some(f=>f.size>IMPORT_FILE))throw new Error("An asset exceeds the 16 MiB tool limit.");
        if(total+sourceBytes>IMPORT_TOTAL)throw new Error("The source and assets are limited to 8 MiB in total (tool policy).");
        showAssets();const read=await Promise.all(files.map(async f=>({...await upload(f),bytes:f.size})));if(mine!==d.assetsTicket)return;
        d.assets=read;if(folder)for(const a of d.assets)a.path=a.path.split("/").slice(1).join("/");dirty(d);}
      catch(e){if(mine!==d.assetsTicket)return;d.assets=[];d.assetsError=`No assets were added: ${e.message||"a file could not be read"}`;box.replaceChildren(stateBox("error","Assets not added.",d.assetsError));}
      finally{if(mine===d.assetsTicket)d.assetsReading=false;showAssets();}}
    const assets=input("assets","","file");assets.multiple=true;assets.addEventListener("change",()=>chooseAssets([...assets.files]));
    const folder=input("asset-folder","","file");folder.multiple=true;folder.setAttribute("webkitdirectory","");folder.addEventListener("change",()=>chooseAssets([...folder.files].filter(f=>/\.(png|tga|sw|ttf|coem)$/i.test(f.name)),true));showAssets();
    form.append(field("Mod source (.c5m)",source,"Read in this browser and sent to the local server only; the file itself is left untouched.",sourceStatus),
      field("Assets (optional)",assets,"The source and assets together are limited to 8 MiB, at most 200 files."),
      field("Or choose an asset folder",folder,"Image, sound, font and map files only. Review their relative paths below.",assetStatus),assetPaths,el("button",{type:"submit",class:"btn",text:"Review import"}),box);
    // Local checks name the control to fix before anything is sent; the server repeats them.
    function preflight(){
      const slug=d.values.slug.trim();
      if(!SLUG_RE.test(slug))return invalid(controlsByKey.slug,"Use 2–48 lowercase letters, digits or underscores, starting with a letter."),false;
      const existing=state.projects.find(x=>x.slug===slug);
      if(existing){invalid(controlsByKey.slug,"A project with this folder name already exists. Choose another name; nothing is overwritten.");
        box.replaceChildren(stateBox("error",`${slug} already exists.`,"Importing never replaces a project. Choose a new folder name above, or open the existing project."),
          existing.ok?link(`Open ${existing.name||slug}`,path("p",slug),"btn btn-small btn-ghost"):null);return false;}
      if(d.sourceReading||d.assetsReading){box.replaceChildren(stateBox("error","Files are still being read.","Wait until the selected files are listed, then review again."));return false;}
      if(!d.source){box.replaceChildren(stateBox("error","Choose a .c5m source file."));reveal(source);return false;}
      const seen=new Set();
      for(const [i,a]of d.assets.entries()){const v=a.path.trim(),c=form.querySelector(`[name="asset-path-${i}"]`);
        const problem=assetPathProblem(v)||(/\.c5m$/i.test(v)?"An asset cannot be a second .c5m.":seen.has(v.toLowerCase())?"Two assets use this path (letter case is ignored).":null);
        if(problem){if(c)invalid(c,problem);box.replaceChildren(stateBox("error","Check the highlighted asset path."));return false;}seen.add(v.toLowerCase());}
      return true;
    }
    form.addEventListener("submit",async e=>{e.preventDefault();if(d.busy||!preflight())return;d.busy=true;
      const controls=[...form.querySelectorAll("input,button")].filter(c=>!box.contains(c));controls.forEach(c=>{c.disabled=true;});
      const strip=f=>({filename:f.filename,base64:f.base64});
      const args={slug:d.values.slug.trim(),source:strip(d.source),assets:d.assets.map(a=>({path:a.path.trim(),base64:a.base64})),name:d.values.name.trim()||null,target_version:d.values.version.trim()||null};
      const unlock=()=>controls.forEach(c=>{c.disabled=false;}),back=()=>{box.replaceChildren();unlock();controlsByKey.slug.focus();};
      // Server failures replace the outcome area (never stack); a known field is marked; the form keeps every value.
      const fail=x=>{const exists=x.code==="dest_exists";box.replaceChildren(exists?stateBox("error",`${args.slug} already exists.`,"Nothing was written. Choose a new folder name above; existing projects are never overwritten."):errorBox(x));
        const c=exists?controlsByKey.slug:fieldControl(form,x.details?.field,x.message);if(c){unlock();invalid(c,exists?"Choose a folder name that is not used yet.":x.message);}
        if(exists)reloadProjects().catch(()=>{});};
      try{const r=await post("preview_import_upload",args);const save=btn("Import reviewed files",async()=>{if(d.busy)return;d.busy=true;save.disabled=true;
        try{const done=await post("import_upload",args);d.done={slug:args.slug,name:args.name||args.slug,revision:done.revision,sha256:done.sha256,files:1+args.assets.length};d.dirty=false;syncDrafts();
          await reloadProjects().catch(()=>{});toast("Import complete.");await render();$("#page-title")?.focus();}
        catch(x){save.disabled=false;fail(x);if(!box.contains(save))box.append(el("div",{class:"btn-row"},btn("Back to the form",back,"btn-ghost")));}finally{d.busy=false;}});
        box.replaceChildren(panel("Review import",table(["Property","Value"],[["Project",r.project],["Source",r.file],["Size",`${r.bytes} bytes`],["Encoding",r.encoding],["Definitions",r.objects],["SHA-256",r.sha256]]),
          table(["Asset","Bytes","Status"],r.assets.map(a=>[a.path,a.bytes,a.problem||a.note||(a.referenced?"Referenced":"Declared export file")])),
          r.missing_assets.length?stateBox("error","Referenced files are missing",r.missing_assets.join(", ")):null,
          r.warnings.length?details(`Warnings (${r.warnings.length})`,el("ul",null,r.warnings.map(w=>el("li",{text:w})))):null,
          el("div",{class:"btn-row"},save,btn("Back to the form",back,"btn-ghost"))));save.focus();}
      catch(x){unlock();fail(x);}finally{d.busy=false;}});
    return stack(el("h1",{id:"page-title",tabindex:"-1",text:"Import a mod"}),panel("Import .c5m",p("Creates a new project from the selected source and assets. Existing projects are never overwritten."),form));
  }
  async function advanced(m,arg,id) {
    if(arg==="source")return sourceView(m,null,true);
    if(arg==="block"){const o=m.objects.find(x=>x.index===Number(id));return o?editor(m,o.kind,o.index):stateBox("error","Block not found.");}
    return stack(el("h2",{text:"Advanced tools"}),panel("All manual commands",p("Edit typed command rows, repeated values, or create a new block. Unknown source is preserved."),
      table(["Definition","Type",""],m.objects.map(o=>[objectLink(m,o),o.kind_label,link("Edit commands",route(m,"author","block",o.index),"btn btn-small btn-ghost")]))),
      panel("Source editing",p("Review an exact source diff before saving."),link("Edit source",route(m,"author","source"),"btn btn-ghost")),
      panel("Mod information",link("Edit mod information",route(m,"mod-info","edit",-1),"btn btn-ghost")),
      panel("Create a definition",el("div",{class:"btn-row"},Object.entries(kinds).filter(([k])=>k!=="global").map(([k,v])=>link(`New ${v[1].toLowerCase()}`,route(m,v[2],"new"),"btn btn-ghost btn-small")))));
  }
  async function render() {
    const version=++seq;closePreview();tabsObserver?.disconnect();let xs;
    try{xs=parts();}catch(e){main.replaceChildren(errorBox(new Error("Malformed address.")));return;}
    renderSidebar(xs[0]==="p"?xs[1]:null);
    for(const a of document.querySelectorAll(".topbar-links a,.sidebar-tools a"))a.setAttribute("aria-current",a.getAttribute("href")===path(xs[0]||"")?"page":"false");
    const activeId=document.activeElement?.id,selection=[document.activeElement?.selectionStart,document.activeElement?.selectionEnd];
    // Focus targets that belong to one page (its title, a linked source line) are never carried over to the next render.
    const keepId=activeId&&!/^(page-title|L\d+)$/.test(activeId)?activeId:null,routeKey=xs.join("/"),routeChanged=routeKey!==state.lastRoute;
    // focus (optional) moves focus to a view's own target, such as the selected definition or linked line, and says whether it did.
    const show=(content,focus)=>{if(version!==seq)return;main.replaceChildren(...(Array.isArray(content)?content:[content]));state.historyNav=false;state.lastRoute=routeKey;
      // A view may name where focus belongs after Back/Forward (for example the catalog row of that history entry).
      if(state.focusTarget){const t=$(state.focusTarget,main);state.focusTarget=null;if(t){t.focus();return;}}
      if(keepId){const target=document.getElementById(keepId);if(target){target.focus();if(typeof selection[0]==="number")target.setSelectionRange?.(...selection);return;}}
      if(focus?.())return;
      ($("#page-title")||main).focus({preventScroll:true});window.scrollTo(0,0);};
    // A page that could not be built at all still has a focusable title, the reason and a way to recover.
    const pageError=(title,e,retry,what)=>show(stack(el("h1",{id:"page-title",tabindex:"-1",text:title}),errorBox(e,retry,what,"page-retry"),
      el("div",{class:"btn-row"},link("Home",path(),"btn btn-small btn-ghost"))));
    if(xs[0]!=="p"){
      try{catalogStatus(null);document.title=xs[0]?`${xs[0]} — KENOGENESIS`:"KENOGENESIS";
        if(xs[0]==="start")show(startView());else if(xs[0]==="import")show(importView());
        else if(xs[0]==="docs")show(stack(el("h1",{id:"page-title",tabindex:"-1",text:"Documentation"}),await docsView(xs[1])));
        else if(xs[0]==="tools")show(toolsView());
        else show(home());
      }catch(e){pageError("This page could not be shown",e,()=>render());}
      return;
    }
    const slug=xs[1],tab=xs[2]||"overview",arg=xs[3],sub=xs[4];lastProject=slug;
    if(!state.models.has(slug))main.replaceChildren(stateBox("loading",`Loading ${slug}…`));
    // The project itself could not be read: there is no shell to keep, so this failure is page-level.
    let m;try{m=await model(slug);}catch(e){if(version!==seq)return;catalogStatus(null);document.title=`${slug} — KENOGENESIS`;
      pageError(`${slug} could not be opened`,e,()=>{state.models.delete(slug);render();},`the project ${slug}`);return;}
    if(version!==seq)return;
    try {
      if(SCOPED_TABS.includes(tab)&&!query().has("c")){
        let remembered=storeGet("localStorage",`kenogenesis:class:${slug}`)||"all";
        try{const saved=JSON.parse(remembered);if(saved && typeof saved === "object")remembered=saved.rev===pinOf(m)?String(saved.value):"all";
          else if(/^\d+$/.test(remembered))remembered="all";}catch(_){if(/^\d+$/.test(remembered))remembered="all";}
        const valid=["all","none",...m.objects.filter(o=>o.kind==="class").map(o=>String(o.index))];
        // Only the class scope is added; references and the revision pin in the address are kept.
        const q=query();q.set("c",valid.includes(remembered)?remembered:"all");if(/^\d+$/.test(q.get("c")))q.set("rev",pinOf(m));history.replaceState(null,"",path(...xs)+`?${q}`);
      }
      carryDrafts(m);
      const guard=state.linkGuard=linkGuard(m,xs);
      if(tab!=="inspector")lastProjectHash.set(slug,location.hash);
      catalogStatus(m);document.title=`${m.project.name} — ${[...groups.flatMap(g=>g[1]),...secondary].find(x=>x[0]===tab)?.[1]||tab} — KENOGENESIS`;
      const body=el("div",{class:"stack"});let content;
      // A section that fails to load (source, design, evidence, docs, catalog…) is reported inside the body, so the project
      // header, tabs and class picker stay usable. Retry re-renders this route with the cached model; drafts are untouched.
      try{
        if(guard.status==="stale")content=staleLink(m,guard,tab);
        else if(tab==="classes"&&!arg&&!["all","none"].includes(scope())){const chosen=m.objects.find(o=>o.kind==="class"&&String(o.index)===scope());content=chosen?detailView(m,chosen):stateBox("empty","Choose a class.");}
        else if(tabKind[tab])content=arg==="new"?editor(m,tabKind[tab],"new",sub):arg==="edit"?editor(m,tabKind[tab],sub):contentList(m,tabKind[tab],arg);
        else if(tab==="overview")content=overview(m,arg);
        else if(tab==="assets")content=assetsView(m);
        else if(tab==="source")content=await sourceView(m,arg);
        else if(tab==="validation")content=await validationView(m);
        else if(tab==="export")content=exportView(m);
        else if(tab==="design")content=await designView(m);
        else if(tab==="evidence")content=await evidenceView(m);
        else if(tab==="author")content=await advanced(m,arg,sub);
        else if(tab==="docs")content=await docsView(arg==="project"?sub:arg,m,arg==="project");
        else if(tab==="inspector")content=await inspector(m,arg,sub);
        else if(tab==="other")content=panel("Other definitions",table(["Definition","Type","Source"],m.objects.filter(o=>["terraingroup"].includes(o.kind)).map(o=>[objectLink(m,o),o.kind_label,sourceLink(m,o.line)])));
        else content=stateBox("error","Unknown section.");
      }catch(e){if(version!==seq)return;content=sectionError(e,sectionResource(tab,arg));}
      if(version!==seq)return;
      if(guard.status==="legacy")body.append(legacyLink(m,guard));
      body.append(content);
      const shell=tab==="inspector"?[el("div",{class:"catalog-head"},link("← Back to project",lastProjectHash.get(slug)||route(m)),el("h1",{id:"page-title",tabindex:"-1",text:"Vanilla catalog"}),p(m.project.name,"faint"))]:projectShell(m,tab);
      // A newly selected definition focuses its own heading; a linked source line takes focus inside its scrolling pane.
      const detailRoute=routeChanged&&tabKind[tab]&&arg!==undefined&&!["new","edit"].includes(arg);
      const staleFocus=()=>{const t=$("#stale-link-h",main);if(t)t.focus();return !!t;};
      show([...shell.filter(Boolean),body],guard.status==="stale"?staleFocus:tab==="source"&&arg?()=>focusSourceLine(Number(arg)):detailRoute?focusDetail:null);syncDrafts();
    } catch(e){pageError(`${m.project.name||slug}: this section could not be shown`,e,()=>{state.models.delete(slug);render();});}
  }
  // Labels for the resource a failed section was loading, used in its error message.
  function sectionResource(tab,arg){
    if(tab==="docs")return arg==="project"?"this private project note":arg?"this guide":"the project guides and notes";
    if(tab==="inspector")return arg==="detail"?"this catalog row":"the vanilla catalog";
    if(tab==="author")return arg==="source"?"the source for editing":"the advanced tools";
    return {source:"the .c5m source",design:"the design report",evidence:"the evidence records",validation:"the validation report"}[tab]||"this section";
  }
  function sectionError(e,what){
    return stack(errorBox(e,()=>render(),what,"section-retry"),p("The project header and its other sections still work. Unsaved drafts in this tab are kept.","faint"));
  }
  // A pin covers definition positions, source lines, numeric class scope and comparison tokens (including catalog rows).
  // Any revision change requires explicit reselection, even in this tab; names never stand in for stable CoE5 identities.
  function linkGuard(m,xs){
    const q=query(),tab=xs[2]||"overview",tail=xs.slice(3),pin=q.get("rev"),pathAt=positional(tab,tail)?(["edit","new","block"].includes(tail[0])?4:3):null;
    const tokens=k=>(q.get(k)||"").split(",").map(t=>t.trim()).filter(t=>/^(?:u|cat):\d+$/.test(t));
    const cmp=/^\d+$/.test(q.get("cmp")||""),classScope=SCOPED_TABS.includes(tab)&&/^\d+$/.test(q.get("c")||"");
    const info={pin,pathAt,target:pathAt===null?null:Number(xs[pathAt]),source:xs[2]==="source",scope:classScope,
      refs:tokens("refs").length+tokens("ref").length,classes:tokens("crefs").length+(cmp?1:0)};
    if(pathAt===null&&!info.refs&&!info.classes&&!classScope)return {status:"none"};
    return {...info,status:pin===pinOf(m)?"ok":pin?"stale":"legacy"};
  }
  const linkWhat=g=>[g.target!==null?`${g.source?"source line":"definition position"} ${g.target}`:null,g.scope?"the class selection":null,
    g.refs?`${g.refs} compared unit${g.refs>1?"s":""}`:null,g.classes?`${g.classes} compared class${g.classes>1?"es":""}`:null].filter(Boolean).join(", ");
  // Show only recovery navigation for a stale address. Lists reset class scope; viewing today's position is an explicit choice.
  function staleLink(m,g,tab){
    const kind=tab==="author"||g.source?null:tabKind[tab],now=g.source||g.target===null?null:m.objects.find(x=>x.index===g.target&&(!kind||x.kind===kind));
    const list=kind?kinds[kind][2]:g.source?"source":tab==="author"?"author":tab;
    const href=path("p",m.project.slug,list)+(SCOPED_TABS.includes(list)?"?c=all":"");
    return el("section",{class:"panel","aria-labelledby":"stale-link-h"},el("h2",{id:"stale-link-h",tabindex:"-1",text:"This link was made for an earlier revision"}),
      stateBox("error","Not opened: positions in this link may name different definitions now.",
        `The address names ${linkWhat(g)} of revision ${g.pin.slice(0,16)}; the saved project is now ${short(m.revision)}. Source order or catalog rows may have changed. Nothing was opened, compared or edited.`),
      el("div",{class:"btn-row"},link(kind?`Open the ${kinds[kind][0].toLowerCase()} list`:g.source?"Open saved source":"Choose again",href,"btn"),
        now?link(`View what is at position ${now.index} now: ${now.display} (line ${now.line})`,kindRoute(m,now),"btn btn-ghost"):null),
      p("Choose again from the saved project; comparisons start empty and drafts in this tab are kept.","faint"));
  }
  // Older links carry no revision: they still open, but say plainly that the positions are unchecked.
  function legacyLink(m,g){
    const keep=btn("Keep this link for the saved revision",()=>{const q=query();q.set("rev",pinOf(m));history.replaceState(history.state,"",path(...parts())+`?${q}`);render();},"btn-small");
    return stack(stateBox("warn","Check this link: it does not record which revision it was made for.",
      `It names ${linkWhat(g)} by position in the saved source. If definitions were added or removed before them since the link was made, it now shows different definitions. Check the names below before relying on it or saving an edit.`),
      el("div",{class:"btn-row"},keep));
  }
  // Focus the selected definition's heading (unit sheet h2 or definition panel h3) instead of the project title.
  function focusDetail(){
    const t=$("#detail-title",main);if(!t)return false;
    window.scrollTo(0,0);t.focus();return true;
  }
  // Focus a linked source line without moving the page: only the code pane scrolls, centring the line in it.
  function focusSourceLine(n){
    if(!Number.isSafeInteger(n)||n<1)return false;
    const row=n&&$(`#L${n}[tabindex]`,main),pane=row?.closest("pre");if(!row||!pane)return false;
    window.scrollTo(0,0);
    pane.scrollTop+=row.getBoundingClientRect().top-pane.getBoundingClientRect().top-(pane.clientHeight-row.offsetHeight)/2;
    row.focus({preventScroll:true});return true;
  }
  window.addEventListener("hashchange",render);
  // History traversal (Back/Forward) precedes its hashchange; views use this to restore focus for that entry.
  // Only entries tagged by a view count: plain link clicks also fire popstate but carry no state.
  window.addEventListener("popstate",e=>{state.historyNav=e.state?.keno===true;});
  document.addEventListener("keydown",e=>{if(e.key!=="/"||/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName))return;
    const search=$('input[type="search"]',main);if(search){e.preventDefault();
      // A collapsed narrow roster hides its search box; open it first.
      if(!search.offsetParent)$(".roster-collapsed .roster-toggle",main)?.click();search.focus();}});
  // Below 820px (CSS) the sidebar stacks above the page; it starts collapsed and collapses again once a link is chosen.
  $(".sidebar-tools").id="sidebar-tools";
  $("#reload-btn").before(el("button",{type:"button",class:"btn btn-small sidebar-toggle",id:"sidebar-toggle",onclick:()=>{sidebarOpen=!sidebarOpen;syncSidebar();}}));
  function syncSidebar() {
    const t=$("#sidebar-toggle");$(".sidebar").classList.toggle("is-collapsed",!sidebarOpen);
    t.setAttribute("aria-controls",["sidebar-tools",$("#project-filter")?"project-filter":null,"project-list"].filter(Boolean).join(" "));
    t.setAttribute("aria-expanded",String(sidebarOpen));t.textContent=sidebarOpen?"Hide projects":"Show projects";
  }
  for(const id of ["#project-list","#sidebar-tools","#catalog-nav"])$(id).addEventListener("click",e=>{if(e.target.closest("a")){sidebarOpen=false;syncSidebar();}});
  syncSidebar();
  // The skip link targets #main, which the hash router would read as a route; move focus without changing the page.
  $(".skip").addEventListener("click",e=>{e.preventDefault();($("#page-title",main)||main).focus();});
  // Startup failure: nothing has been edited yet, so reloading the page is the recovery; the title takes focus.
  (async()=>{try{state.meta=await get("/api/meta");await reloadProjects();await render();}catch(e){
    main.replaceChildren(el("h1",{id:"page-title",tabindex:"-1",text:"KENOGENESIS could not start"}),errorBox(e,()=>location.reload(),"the workshop"));$("#page-title",main).focus();}})();
})();
