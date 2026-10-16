"use strict";
const $ = id => document.getElementById(id);
let current = null, registry = [], selected = null, pending = null, busy = false;
const token = document.querySelector('meta[name="kenogenesis-token"]').content;

function status(message, error = false) {
  $("status").textContent = message;
  $("status").classList.toggle("error", error);
}

async function api(operation, args = {}, write = false) {
  const options = write ? {method: "POST", headers: {"Content-Type": "application/json", "X-Kenogenesis-Token": token}, body: JSON.stringify(args)} : {};
  const url = `/api/${operation}` + (write ? "" : `?args=${encodeURIComponent(JSON.stringify(args))}`);
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!payload.ok) {
    if (payload.error.code === "stale_revision" && current) {
      $("stale-draft").hidden = false;
      $("stale-draft-text").textContent = `Project: ${current.project}\n\nSource draft:\n${$("source-text").value}\n\nPending change:\n${JSON.stringify(pending, null, 2)}\n\nPreview diff:\n${$("diff").textContent}`;
    }
    throw new Error(`${payload.error.code}: ${payload.error.message || "Operation failed"}`);
  }
  return payload.result;
}

// Keep user drafts intact on failures, especially revision conflicts.
async function action(fn) {
  if (busy) return;
  busy = true;
  document.body.setAttribute("aria-busy", "true");
  try { await fn(); } catch (error) { status(error.message, true); }
  finally { busy = false; document.body.removeAttribute("aria-busy"); }
}

function panel(name) {
  document.querySelectorAll(".panel").forEach(el => el.hidden = el.id !== name);
  document.querySelectorAll("[data-panel]").forEach(el => el.setAttribute("aria-pressed", String(el.dataset.panel === name)));
}

function diagnostics(report) {
  $("diagnostics").replaceChildren();
  for (const d of report.diagnostics) {
    const li = document.createElement("li");
    li.className = d.severity;
    li.textContent = `${d.severity.toUpperCase()} · ${d.message}`;
    const detail = document.createElement("small");
    detail.textContent = `${d.file}${d.line ? `:${d.line}` : ""} · ${d.code}`;
    li.append(detail); $("diagnostics").append(li);
  }
  if (!report.diagnostics.length) $("diagnostics").textContent = "No static diagnostics in the supported subset.";
}

async function projects(choose = "") {
  const result = await api("list_projects");
  $("project").replaceChildren(new Option("Choose a project", ""));
  for (const p of result.projects) $("project").add(new Option(`${p.name} (${p.slug})`, p.slug));
  if (choose) $("project").value = choose;
  status(result.projects.length ? "Choose a project to inspect its saved source." : "No projects yet. Create one here, or import a mod with the CLI.");
}

async function load(slug) {
  if (!slug) { current = null; $("project-content").hidden = true; return; }
  status("Loading saved project…");
  const result = await api("project_view", {project: slug});
  current = result; pending = null; selected = null;
  $("project-content").hidden = false;
  $("project-name").textContent = result.metadata.name;
  $("coverage").textContent = `Game ${result.metadata.target_version || "version not recorded"} · Manual ${result.manual.version} · Static evidence only`;
  const c = result.validation.counts;
  $("counts").textContent = `${result.objects.length} objects · ${c.error} errors · ${c.warning} warnings · ${c.unverified} unverified`;
  $("source-text").value = result.source;
  $("apply").disabled = true; $("diff").textContent = "";
  $("review-note").textContent = "Preview an edit to see its exact changes here.";
  $("object-title").textContent = "Choose an object"; $("object-source").textContent = ""; $("fields").hidden = true;
  diagnostics(result.validation); renderObjects(); renderCommands();
  $("catalog-status").textContent = result.catalog.available ? `Local catalog: ${result.catalog.game_version}, ${result.catalog.rows} rows. Provenance: ${JSON.stringify(result.catalog.provenance)}` : result.catalog.note;
  const form = $("settings-form");
  form.elements.target_version.value = result.metadata.target_version || "";
  form.elements.dependencies.value = result.metadata.dependencies.join("\n");
  form.elements.catalog.value = result.metadata.catalog || "";
  form.elements.declared_assets.value = result.metadata.declared_assets.join("\n");
  status("Saved project loaded. Edits require preview before saving.");
}

function renderObjects() {
  const query = $("object-filter").value.toLowerCase();
  $("objects").replaceChildren();
  for (const obj of current.objects.filter(o => `${o.kind} ${o.name}`.toLowerCase().includes(query))) {
    const button = document.createElement("button");
    button.textContent = obj.name || `${obj.kind} ${obj.index + 1}`;
    const small = document.createElement("small"); small.textContent = `${obj.kind} · line ${obj.line}`;
    button.append(small); button.setAttribute("aria-pressed", String(selected?.index === obj.index));
    button.addEventListener("click", () => chooseObject(obj)); $("objects").append(button);
  }
  if (!$("objects").children.length) $("objects").textContent = "No matching objects. Add definitions in Source.";
}

function chooseObject(obj) {
  selected = obj; renderObjects();
  $("object-title").textContent = obj.name || obj.kind;
  $("object-note").textContent = `${obj.kind} · ${obj.opener} · line ${obj.line}. Values shown are authored commands; inherited values are not resolved.`;
  const lines = current.source.split(/\r?\n/);
  const next = current.objects[obj.index + 1];
  $("object-source").textContent = lines.slice(obj.line - 1, next ? next.line - 1 : lines.length).join("\n");
  const fields = registry.filter(s => s.context === obj.kind && !s.repeat && !["copystats", "copyspr", "clearweapons", "clearspec", "clearrec", "clearstartunits", "clearstartterr"].includes(s.command));
  $("field-command").replaceChildren();
  for (const s of fields) $("field-command").add(new Option(s.command, s.command));
  $("fields").hidden = !fields.length; renderArguments();
}

function renderArguments() {
  const spec = registry.find(s => s.context === selected?.kind && s.command === $("field-command").value);
  $("field-args").replaceChildren();
  if (!spec) return;
  const authored = selected.statements.filter(st => st.command === spec.command).at(-1);
  spec.args.forEach((signature, index) => {
    const label = document.createElement("label"); label.textContent = `${signature.startsWith("s") ? "Text" : "Value"} ${index + 1}${signature.endsWith("?") ? " (optional)" : ""}`;
    const input = document.createElement("input"); input.dataset.signature = signature;
    input.type = signature.startsWith("i") ? "number" : "text";
    input.required = !signature.endsWith("?"); input.value = authored?.args[index]?.value ?? "";
    const bounds = signature.replace("?", "").split(":");
    if (bounds.length === 3) { input.min = bounds[1]; input.max = bounds[2]; }
    label.append(input); $("field-args").append(label);
  });
  $("field-help").textContent = `Manual ${spec.manual.version}, p. ${spec.page}. ${spec.note || "Only this explicit field changes."}`;
}

function renderCommands() {
  const query = $("command-filter").value.toLowerCase();
  $("command-results").replaceChildren();
  for (const spec of registry.filter(s => `${s.command} ${s.context}`.includes(query))) {
    const article = document.createElement("article"), code = document.createElement("code"), p = document.createElement("p");
    code.textContent = `${spec.command} ${spec.args.join(" ")}`;
    p.className = "muted"; p.textContent = `${spec.context} · manual p. ${spec.page}${spec.note ? ` · ${spec.note}` : ""}`;
    article.append(code, p); $("command-results").append(article);
  }
}

function previewResult(kind, args, result) {
  pending = {kind, args}; $("diff").textContent = result.diff || "No changes.";
  $("review-note").textContent = "Review this change. Saving will reject a stale revision; your draft will remain available.";
  $("apply").disabled = !result.diff;
  if (result.validation) diagnostics(result.validation);
  panel("review"); status("Preview ready. Nothing has been saved.");
}

// Derive one bounded replacement while retaining the saved file's newline convention.
function sourcePatch(before, entered) {
  if (before.includes("\r\n") && /(?<!\r)\n/.test(before)) throw new Error("This source has mixed line endings. Use a targeted CLI patch to preserve its existing bytes.");
  const after = before.includes("\r\n") ? entered.replace(/\r?\n/g, "\r\n") : entered;
  let start = 0, endBefore = before.length, endAfter = after.length;
  while (start < endBefore && start < endAfter && before[start] === after[start]) start++;
  while (endBefore > start && endAfter > start && before[endBefore - 1] === after[endAfter - 1]) { endBefore--; endAfter--; }
  if (start === endBefore && start === endAfter) throw new Error("No source changes to preview.");
  // Include full lines to give insertions a nonempty, reviewable anchor.
  start = before.lastIndexOf("\n", start - 1) + 1;
  if (start === before.length && before.length) start = start < 2 ? 0 : before.lastIndexOf("\n", start - 2) + 1;
  const suffix = before.indexOf("\n", endBefore);
  if (suffix !== -1) { endAfter += suffix + 1 - endBefore; endBefore = suffix + 1; }
  let old = before.slice(start, endBefore);
  while (old && before.split(old).length > 2) {
    const previous = before.lastIndexOf("\n", start - 2) + 1;
    const next = before.indexOf("\n", endBefore);
    if (previous < start) start = previous;
    else if (next !== -1) { endAfter += next + 1 - endBefore; endBefore = next + 1; }
    else { start = 0; endBefore = before.length; endAfter = after.length; }
    old = before.slice(start, endBefore);
  }
  return {old, new: after.slice(start, endAfter)};
}

document.querySelectorAll("[data-panel]").forEach(button => button.addEventListener("click", () => panel(button.dataset.panel)));
$("project").addEventListener("change", () => action(() => load($("project").value)));
$("reload").addEventListener("click", () => action(() => load($("project").value)));
$("object-filter").addEventListener("input", renderObjects);
$("command-filter").addEventListener("input", renderCommands);
$("field-command").addEventListener("change", renderArguments);
$("create").addEventListener("submit", event => { event.preventDefault(); action(async () => {
  const f = event.target.elements;
  await api("create_project", {slug: f.slug.value, name: f.name.value || null, target_version: f.version.value || null}, true);
  await projects(f.slug.value); await load(f.slug.value); panel("source");
}); });
$("fields").addEventListener("submit", event => { event.preventDefault(); action(async () => {
  const values = [...$("field-args").querySelectorAll("input")].filter(input => input.value !== "").map(input => input.type === "number" ? Number(input.value) : input.value);
  const args = {project: current.project, expected_revision: current.revision, object_index: selected.index, command: $("field-command").value, arguments: values};
  previewResult("fields", args, await api("preview_fields", args, true));
}); });
$("preview-source").addEventListener("click", () => action(async () => {
  const args = {project: current.project, expected_revision: current.revision, ...sourcePatch(current.source, $("source-text").value)};
  previewResult("patch", args, await api("preview_patch", args, true));
}));
$("settings-form").addEventListener("submit", event => { event.preventDefault(); action(async () => {
  const f = event.target.elements, lines = v => v.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  const args = {project: current.project, expected_revision: current.revision, dependencies: lines(f.dependencies.value), target_version: f.target_version.value || null, catalog: f.catalog.value, declared_assets: lines(f.declared_assets.value), preview: true};
  previewResult("settings", args, await api("configure_project", args, true));
}); });
$("apply").addEventListener("click", () => action(async () => {
  if (!pending) return;
  const operation = pending.kind === "settings" ? "configure_project" : `apply_${pending.kind}`;
  await api(operation, {...pending.args, ...(pending.kind === "settings" ? {preview: false} : {})}, true);
  const slug = current.project; await load(slug); panel("review"); status("Reviewed change saved. A source backup is kept locally.");
}));
$("export").addEventListener("click", () => action(async () => {
  const result = await api("export_mod", {project: current.project, expected_revision: current.revision, format: $("export-format").value}, true);
  $("export-result").textContent = `Created: ${result.path}\nManifest: ${result.manifest}\n${result.archive_sha256 ? `SHA-256: ${result.archive_sha256}\n` : ""}Static checks only. Test the exported package in CoE5.`;
  status("Export created from the saved revision.");
}));
$("compatibility").addEventListener("click", () => action(async () => { $("compatibility-result").textContent = JSON.stringify(await api("compatibility", {project: current.project}), null, 2); }));
$("catalog-search").addEventListener("submit", event => { event.preventDefault(); action(async () => { $("catalog-results").textContent = JSON.stringify(await api("search_game_data", {project: current.project, query: event.target.elements.query.value}), null, 2); }); });
action(async () => { registry = (await api("lookup_command")).entries; await projects(); });
