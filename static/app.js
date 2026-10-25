const $ = (id) => document.getElementById(id);
let currentDraft = [];
let tasksCache = [];
let toastTimer;

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
}
function duration(minutes) {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}
async function api(url, options = {}) {
  const response = await fetch(url, {headers: {"Content-Type":"application/json"}, ...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Something went wrong.");
  return data;
}
function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === `view-${name}`));
  document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.view === name));
  if (name === "tasks") loadTasks();
  if (name === "reset") loadReset();
}
document.querySelectorAll(".nav-item").forEach(btn => btn.addEventListener("click", () => showView(btn.dataset.view)));
$("brain-dump").addEventListener("input", () => $("char-count").textContent = `${$("brain-dump").value.length.toLocaleString()} / 12,000`);
$("example-btn").addEventListener("click", () => {
  $("brain-dump").value = "Finish my project report by tomorrow. Prepare for a backend interview. Reply to my mentor about the internship. Clean up my downloads folder. Spend 30 minutes revising SQL.";
  $("brain-dump").dispatchEvent(new Event("input"));
});
$("plan-btn").addEventListener("click", async () => {
  const text = $("brain-dump").value.trim();
  if (text.length < 3) return toast("Add a few notes first.");
  const btn = $("plan-btn");
  btn.disabled = true; btn.querySelector("span").textContent = "Making your plan…";
  try {
    const result = await api("/api/plan", {method:"POST", body:JSON.stringify({text})});
    currentDraft = result.tasks.map((t, i) => ({...t, selected:true, draftId:i}));
    $("plan-output").classList.add("hidden");
    $("draft-count").textContent = `${currentDraft.length} draft tasks`;
    $("plan-summary").textContent = `${result.summary} Estimated total: ${duration(result.estimated_total_minutes)}. ${result.engine === "ollama" ? "Generated with your local AI model." : "Generated with the built-in offline rules engine."}`;
    $("plan-summary").classList.remove("hidden");
    renderDraft();
    $("save-all-wrap").classList.remove("hidden");
    toast("Your draft plan is ready to review.");
  } catch (e) { toast(e.message); }
  finally { btn.disabled = false; btn.querySelector("span").textContent = "Turn this into a plan"; }
});
function renderDraft() {
  $("draft-tasks").innerHTML = currentDraft.map((t, i) => `
    <div class="draft-task">
      <input type="checkbox" aria-label="Select ${escapeHtml(t.title)}" data-draft-check="${i}" ${t.selected ? "checked" : ""}>
      <div><strong>${escapeHtml(t.title)}</strong><p>${escapeHtml(t.details || "A small next step you can adjust.")}</p></div>
      <span class="priority ${t.priority}">${escapeHtml(t.priority)}</span><span class="estimate">${duration(t.estimate_minutes)}</span>
    </div>`).join("");
  document.querySelectorAll("[data-draft-check]").forEach(cb => cb.addEventListener("change", () => {currentDraft[Number(cb.dataset.draftCheck)].selected = cb.checked;}));
}
$("save-all-btn").addEventListener("click", async () => {
  const selected = currentDraft.filter(t => t.selected);
  if (!selected.length) return toast("Select at least one task to save.");
  const btn = $("save-all-btn"); btn.disabled = true;
  try {
    for (const task of selected) {
      await api("/api/tasks", {method:"POST", body:JSON.stringify({title:task.title, details:task.details, priority:task.priority, estimate_minutes:task.estimate_minutes})});
    }
    toast(`${selected.length} task${selected.length === 1 ? "" : "s"} saved.`);
    currentDraft = [];
    $("draft-tasks").innerHTML = "";
    $("plan-summary").classList.add("hidden");
    $("save-all-wrap").classList.add("hidden");
    $("plan-output").classList.remove("hidden");
    $("draft-count").textContent = "Waiting for your notes";
    await loadTasks();
    showView("tasks");
  } catch(e) { toast(e.message); }
  finally { btn.disabled = false; }
});
async function loadTasks() {
  try {
    tasksCache = await api("/api/tasks");
    const open = tasksCache.filter(t => t.status === "todo"), done = tasksCache.filter(t => t.status === "done");
    $("task-count").textContent = open.length;
    $("open-stat").textContent = open.length;
    $("done-stat").textContent = done.length;
    $("time-stat").textContent = duration(open.reduce((n,t)=>n+t.estimate_minutes,0));
    $("task-list").innerHTML = tasksCache.length ? tasksCache.map(taskRow).join("") : `<div class="empty-list">No tasks yet. Start with a brain dump or add one small task.</div>`;
    wireTaskRows($("task-list"));
  } catch(e) { toast(e.message); }
}
function taskRow(t) {
  return `<div class="task-row ${t.status === "done" ? "done" : ""}">
    <input class="task-check" type="checkbox" data-toggle="${t.id}" aria-label="Mark ${escapeHtml(t.title)} complete" ${t.status === "done" ? "checked" : ""}>
    <div class="task-body"><strong>${escapeHtml(t.title)}</strong>${t.details ? `<p>${escapeHtml(t.details)}</p>` : ""}
      <div class="task-meta"><span class="priority ${t.priority}">${escapeHtml(t.priority)}</span><span class="estimate">${duration(t.estimate_minutes)}</span>${t.due_date ? `<span class="estimate">Due ${escapeHtml(t.due_date)}</span>` : ""}</div>
    </div><div class="task-actions"><button class="icon-btn" data-delete="${t.id}" aria-label="Delete task">×</button></div>
  </div>`;
}
function wireTaskRows(container) {
  container.querySelectorAll("[data-toggle]").forEach(cb => cb.addEventListener("change", async () => {
    try { await api(`/api/tasks/${cb.dataset.toggle}`, {method:"PATCH",body:JSON.stringify({status:cb.checked ? "done" : "todo"})}); await loadTasks(); if ($("view-reset").classList.contains("active")) await loadReset(); }
    catch(e) { toast(e.message); }
  }));
  container.querySelectorAll("[data-delete]").forEach(btn => btn.addEventListener("click", async () => {
    try { await api(`/api/tasks/${btn.dataset.delete}`, {method:"DELETE"}); await loadTasks(); if ($("view-reset").classList.contains("active")) await loadReset(); toast("Task deleted."); }
    catch(e) { toast(e.message); }
  }));
}
$("add-task-btn").addEventListener("click", () => { $("add-task-form").classList.remove("hidden"); $("new-title").focus(); });
$("cancel-add").addEventListener("click", () => $("add-task-form").classList.add("hidden"));
$("create-task-btn").addEventListener("click", async () => {
  const title = $("new-title").value.trim();
  if (!title) return toast("Give your task a title.");
  try {
    await api("/api/tasks", {method:"POST",body:JSON.stringify({title,details:$("new-details").value,priority:$("new-priority").value,estimate_minutes:Number($("new-estimate").value)})});
    $("new-title").value = ""; $("new-details").value = ""; $("add-task-form").classList.add("hidden");
    await loadTasks(); toast("Task added.");
  } catch(e) { toast(e.message); }
});
async function loadReset() {
  try {
    const data = await api("/api/reset");
    $("reset-date").textContent = new Date(`${data.date}T12:00:00`).toLocaleDateString(undefined,{weekday:"long",month:"long",day:"numeric"});
    $("reset-open").textContent = data.open_count;
    $("reset-time").textContent = duration(data.estimated_minutes);
    $("reset-message").textContent = data.message;
    $("reset-list").innerHTML = data.tasks.length ? data.tasks.slice(0,5).map(taskRow).join("") : `<div class="empty-list">You're clear for now. Take a breath, or add one small goal for today.</div>`;
    wireTaskRows($("reset-list"));
  } catch(e) { toast(e.message); }
}
$("reset-refresh").addEventListener("click", loadReset);
async function init() {
  $("today-label").textContent = new Date().toLocaleDateString(undefined,{weekday:"long",month:"short",day:"numeric"}).toUpperCase();
  try {
    const health = await api("/api/health");
    $("engine-status").textContent = health.ollama_available ? `Local AI ready · ${health.model}` : "Offline mode ready";
  } catch { $("engine-status").textContent = "Local mode ready"; }
  await loadTasks();
}
init();
