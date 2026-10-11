// Stoa front end: a small hash-routed app, no build step.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const view = $("#view");

const VIRTUE_ORDER = ["wisdom", "courage", "justice", "temperance"];
const PILLARS = [
  ["philosophy", "Philosophy"], ["exercise", "Exercise"], ["rest", "Rest"], ["recovery", "Recovery"],
];
// Four series can't all be told apart by hue alone under colour-blindness; the fourth also gets a dash.
const DASHED = new Set(["temperance", "recovery"]);
const state = { meta: null, date: null, charts: [], trendDays: 90 };

// ---------- helpers ----------
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim(); }
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 2600);
}
async function api(path, opts = {}) {
  const init = { credentials: "same-origin", ...opts };
  if (opts.json !== undefined) {
    init.body = JSON.stringify(opts.json);
    init.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    init.method = opts.method || "POST";
  }
  const res = await fetch(path, init);
  if (res.status === 401) { renderLogin(); throw new Error("Not signed in"); }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error(data?.detail || res.statusText);
  return data;
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
function addDays(iso, n) { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }
function fmtDate(iso, opts = { weekday: "long", month: "long", day: "numeric" }) {
  return new Date(iso + "T12:00:00").toLocaleDateString(undefined, opts);
}
function fmtTime(isoDT) { return new Date(isoDT).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }); }
function hours(sec) { return sec ? (sec / 3600).toFixed(1) : null; }
function n(v, digits = 0) { return v === null || v === undefined ? "—" : Number(v).toFixed(digits); }
function virtueChip(v) {
  if (!v) return "";
  const name = state.meta?.virtues?.[v]?.name || v;
  return `<span class="chip v-${v}"><span class="dot"></span>${esc(name)}</span>`;
}
function rolling(values, w = 7) {
  return values.map((_, i) => {
    const win = values.slice(Math.max(0, i - w + 1), i + 1).filter((x) => x !== null && x !== undefined);
    return win.length ? +(win.reduce((a, b) => a + b, 0) / win.length).toFixed(1) : null;
  });
}
function destroyCharts() { state.charts.forEach((c) => c.destroy()); state.charts = []; }

// ---------- router ----------
const routes = { today: renderToday, review: renderReview, trends: renderTrends, calendar: renderCalendar, settings: renderSettings };
async function route() {
  const [name, query] = (location.hash.replace(/^#\/?/, "") || "today").split("?");
  const key = routes[name] ? name : "today";
  $$(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === key));
  destroyCharts();
  try { await routes[key](new URLSearchParams(query || "")); }
  catch (e) { if (e.message !== "Not signed in") view.innerHTML = `<div class="card">Something went wrong: ${esc(e.message)}</div>`; }
  view.focus({ preventScroll: true });
}

// ---------- login ----------
function renderLogin() {
  $(".nav").style.display = "none";
  view.innerHTML = `
    <form class="card login stack" id="login">
      <h1>Stoa</h1>
      <p class="muted">"Waste no more time arguing what a good man should be. Be one."</p>
      <div><label for="pw">Password</label><input id="pw" type="password" autocomplete="current-password" required></div>
      <button class="btn primary" type="submit">Enter</button>
    </form>`;
  $("#login").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/login", { json: { password: $("#pw").value } });
      $(".nav").style.display = "";
      await boot();
    } catch (err) { toast(err.message); }
  };
}

// ---------- Today ----------
async function renderToday(params) {
  state.date = params.get("date") || state.date || state.meta.today;
  const d = await api(`/api/today?date=${state.date}`);
  const { insight, journal, health, pillars } = d;
  const isToday = d.date === state.meta.today;
  const q = insight.quote;
  const focus = insight.focus;

  view.innerHTML = `
    <div class="page-head">
      <div>
        <h1>${esc(fmtDate(d.date))}</h1>
        <div class="sub">Week ${focus.week_of_cycle} of ${focus.cycle_length} · focus on <b>${esc(focus.franklin)}</b> ${virtueChip(focus.virtue)}</div>
      </div>
      <div class="row">
        <button class="btn icon" id="prev" aria-label="Previous day">‹</button>
        ${isToday ? "" : `<button class="btn" id="go-today">Today</button>`}
        <button class="btn icon" id="next" aria-label="Next day" ${isToday ? "disabled" : ""}>›</button>
      </div>
    </div>

    <div class="grid two">
      <section class="card">
        <h2>Daily insight ${virtueChip(q.virtue)}</h2>
        <blockquote class="quote" style="margin:0">“${esc(q.text)}”</blockquote>
        <div class="quote-by">${esc(q.author)} · ${esc(q.source)}</div>
        <label class="practice">
          <input type="checkbox" id="practice_done" ${journal.practice_done ? "checked" : ""}>
          <span><b>Practice:</b> ${esc(q.practice)}</span>
        </label>
      </section>

      <section class="card">
        <h2>Today's balance <span class="hint">${insight.state === "unknown" ? "no recovery data" : `body says: ${esc(insight.state)}`}</span></h2>
        <div class="pillars">
          ${PILLARS.map(([k, label]) => `
            <div class="pillar p-${k}">
              <div class="name"><span class="key"></span>${label}</div>
              <div class="val">${pillars[k] === null ? "—" : Math.round(pillars[k])}<small>${pillars[k] === null ? "" : "/100"}</small></div>
              <div class="meter"><span style="width:${pillars[k] ?? 0}%"></span></div>
            </div>`).join("")}
        </div>
        <div style="margin-top:14px">
          ${insight.recommendations.map((r) => `
            <div class="rec v-${r.virtue || ""}"><span class="bar"></span>
              <div><h3>${esc(r.title)}</h3><p>${esc(r.detail)}</p></div></div>`).join("")}
        </div>
      </section>

      <section class="card">
        <h2>Morning <span class="hint">${esc(insight.morning_question)}</span></h2>
        <div class="stack">
          <textarea id="morning_intention" placeholder="The good I will do today…">${esc(journal.morning_intention)}</textarea>
          <div>
            <label for="premeditatio">Premeditatio malorum: what might go wrong, and how will you meet it?</label>
            <textarea id="premeditatio" placeholder="If the meeting runs long, I will…">${esc(journal.premeditatio)}</textarea>
          </div>
        </div>
        <div id="today-cal" class="small" style="margin-top:12px"></div>
      </section>

      <section class="card">
        <h2>Body <span class="hint">${health ? `from ${esc(health.source)}` : `<a href="#/settings">connect Garmin</a>`}</span></h2>
        ${healthStats(health, d.hrv_baseline)}
        ${d.activities.length ? `<div style="margin-top:12px" class="small">${d.activities.map((a) =>
          `<div class="row"><b>${esc(a.name || a.type)}</b><span class="muted">${Math.round((a.duration_s || 0) / 60)} min${a.avg_hr ? ` · ${a.avg_hr} bpm` : ""}</span></div>`).join("")}</div>` : ""}
      </section>

      <section class="card span-2">
        <h2>Evening examination <span class="hint">${esc(insight.evening_question)}</span></h2>
        <div class="grid two">
          <div>
            <div class="row" style="margin-bottom:8px">
              <span class="small muted">Tap to mark: ✓ kept · each dot a lapse (Franklin's method)</span>
              <span class="spacer"></span>
              <button class="btn ghost small" id="all-kept">All kept</button>
            </div>
            <div id="checklist"></div>
          </div>
          <div class="stack">
            <div><label for="evening_review">What good have I done today?</label>
              <textarea id="evening_review" rows="4">${esc(journal.evening_review)}</textarea></div>
            <div><label for="gratitude">Gratitude</label>
              <textarea id="gratitude" rows="2">${esc(journal.gratitude)}</textarea></div>
            <div><label>Mood</label>${scale("mood", journal.mood)}</div>
            <div><label>Tranquility (undisturbed by trifles)</label>${scale("tranquility", journal.tranquility)}</div>
            <div class="saved" id="saved"></div>
          </div>
        </div>
      </section>
    </div>`;

  $("#prev").onclick = () => { location.hash = `#/today?date=${addDays(d.date, -1)}`; };
  $("#next").onclick = () => { location.hash = `#/today?date=${addDays(d.date, 1)}`; };
  $("#go-today")?.addEventListener("click", () => { state.date = state.meta.today; location.hash = "#/today"; });

  // Journal autosave
  const save = debounce(async (patch) => {
    await api(`/api/journal/${d.date}`, { method: "PUT", json: patch });
    $("#saved").textContent = `Saved ${new Date().toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  }, 600);
  ["morning_intention", "premeditatio", "evening_review", "gratitude"].forEach((id) => {
    $(`#${id}`).addEventListener("input", (e) => save({ [id]: e.target.value }));
  });
  $("#practice_done").onchange = (e) => save({ practice_done: e.target.checked ? 1 : 0 });
  $$(".scale").forEach((el) => el.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    $$("button", el).forEach((x) => x.classList.toggle("on", x === b));
    save({ [el.dataset.field]: +b.dataset.v });
  }));

  // Franklin checklist
  const evals = { ...d.evaluations };
  const drawChecklist = () => {
    $("#checklist").innerHTML = VIRTUE_ORDER.map((v) => {
      const items = d.behaviors.filter((b) => b.virtue === v);
      if (!items.length) return "";
      return `<div class="virtue-group v-${v}"><h3>${virtueChip(v)}</h3>
        ${items.map((b) => `<div class="behavior">
          <div class="q"><b>${esc(b.title)}</b><span>${esc(b.question)}</span></div>
          ${lapseButton(b.id, evals[b.id])}</div>`).join("")}</div>`;
    }).join("");
  };
  drawChecklist();
  const saveEvals = debounce((patch) => api(`/api/evaluations/${d.date}`, { method: "PUT", json: { lapses: patch } }), 300);
  let pending = {};
  $("#checklist").addEventListener("click", (e) => {
    const b = e.target.closest(".lapse"); if (!b) return;
    const id = +b.dataset.id;
    const cur = evals[id];
    // unset → ✓ → • → •• → ••• → ✓
    const next = cur === undefined || cur === null ? 0 : cur >= 3 ? 0 : cur + 1;
    evals[id] = next; pending[id] = next;
    b.outerHTML = lapseButton(id, next);
    saveEvals(pending); pending = { ...pending };
  });
  $("#all-kept").onclick = async () => {
    d.behaviors.forEach((b) => { if (evals[b.id] === undefined) evals[b.id] = 0; });
    await api(`/api/evaluations/${d.date}`, { method: "PUT", json: { lapses: evals } });
    drawChecklist(); toast("Marked unmarked items as kept");
  };

  loadTodayCalendar(d.date);
}

function lapseButton(id, v) {
  if (v === undefined || v === null) return `<button class="lapse unset" data-id="${id}" aria-label="Not yet evaluated">mark</button>`;
  if (v === 0) return `<button class="lapse clean" data-id="${id}" aria-label="Kept">✓</button>`;
  return `<button class="lapse" data-id="${id}" aria-label="${v} lapses">${'<i class="pip"></i>'.repeat(v)}</button>`;
}
function scale(field, value) {
  return `<div class="scale" data-field="${field}">${[1, 2, 3, 4, 5].map((i) =>
    `<button type="button" data-v="${i}" class="${value === i ? "on" : ""}" aria-label="${field} ${i}">${i}</button>`).join("")}</div>`;
}
function healthStats(h, baseline) {
  if (!h) return `<div class="empty-state small">No health data for this day yet.<br>Garmin syncs automatically each morning, or upload a CSV in Settings.</div>`;
  const hrvDelta = h.hrv_ms && baseline ? Math.round((h.hrv_ms / baseline - 1) * 100) : null;
  const stat = (label, value, unit = "", extra = "") =>
    `<div class="stat"><div class="label">${label}</div><div class="value">${value}<small> ${unit}</small> ${extra}</div></div>`;
  return `<div class="stats">
    ${stat("Sleep", hours(h.sleep_seconds) ?? "—", "h", h.sleep_score ? `<small>· score ${h.sleep_score}</small>` : "")}
    ${stat("HRV", n(h.hrv_ms), "ms", hrvDelta === null ? "" : `<small class="${hrvDelta >= 0 ? "delta-up" : "delta-down"}">${hrvDelta >= 0 ? "▲" : "▼"} ${Math.abs(hrvDelta)}% vs 30d</small>`)}
    ${stat("Resting HR", n(h.resting_hr), "bpm")}
    ${stat("Body Battery", h.body_battery_high ?? "—", "", h.body_battery_low != null ? `<small>low ${h.body_battery_low}</small>` : "")}
    ${stat("Readiness", n(h.training_readiness))}
    ${stat("Stress", n(h.stress_avg), "avg")}
    ${stat("Steps", h.steps != null ? Number(h.steps).toLocaleString() : "—")}
    ${stat("Intensity", n(h.intensity_minutes), "min")}
    ${stat("VO₂ max", n(h.vo2max, 1))}
  </div>`;
}
async function loadTodayCalendar(date) {
  const box = $("#today-cal"); if (!box) return;
  try {
    const c = await api("/api/calendar/opportunities?days=1");
    if (!c.connected) { box.innerHTML = `<span class="muted">Connect Google Calendar in <a href="#/settings">Settings</a> to see today's chances to practise.</span>`; return; }
    const items = c.events.filter((e) => e.practice && e.start.slice(0, 10) === date).slice(0, 4);
    box.innerHTML = items.length
      ? `<h3 style="margin-bottom:4px">Chances to practise today</h3>` + items.map((e) =>
        `<div class="rec v-${e.virtue}"><span class="bar"></span><div><b>${e.all_day ? "" : esc(fmtTime(e.start)) + " · "}${esc(e.summary)}</b><p>${esc(e.practice)}</p></div></div>`).join("")
      : `<span class="muted">A quiet calendar today. A good day for deep work and a long session.</span>`;
  } catch (e) { box.innerHTML = `<span class="muted">Calendar unavailable: ${esc(e.message)}</span>`; }
}

// ---------- Franklin weekly review ----------
async function renderReview(params) {
  const start = params.get("start") || state.meta.today;
  const w = await api(`/api/week?start=${start}`);
  const f = w.focus;
  const precept = state.meta.franklin.find((x) => x.name === f.franklin)?.precept || "";
  view.innerHTML = `
    <div class="page-head">
      <div><h1>Franklin's book</h1>
        <div class="sub">Week of ${esc(fmtDate(w.start, { month: "long", day: "numeric" }))} · ${esc(f.franklin)} ${virtueChip(f.virtue)}</div></div>
      <div class="row">
        <button class="btn icon" id="pw" aria-label="Previous week">‹</button>
        <button class="btn" id="tw">This week</button>
        <button class="btn icon" id="nw" aria-label="Next week">›</button>
      </div>
    </div>
    <section class="card" style="margin-bottom:14px">
      <p class="quote" style="font-size:1.1rem">${esc(f.franklin)}. ${esc(precept)}</p>
      <p class="small muted" style="margin-top:6px">Franklin gave each virtue a week of strict attention, marking a dot for every fault, and
      aimed for a clean line before moving on. Here his 13 virtues sit beneath the four Stoic ones. Tap a cell to add a lapse.</p>
    </section>
    <section class="card table-scroll">
      <table class="franklin">
        <thead><tr><th>Behaviour</th>${w.days.map((d) =>
          `<th>${esc(fmtDate(d, { weekday: "short" }))}<br><span class="muted">${d.slice(8)}</span></th>`).join("")}<th>Σ</th></tr></thead>
        <tbody>${w.behaviors.map((b) => {
          const row = w.grid[b.id] || {};
          const total = Object.values(row).reduce((a, x) => a + x, 0);
          const isFocus = b.franklin === f.franklin || (!w.behaviors.some((x) => x.franklin === f.franklin) && b.virtue === f.virtue);
          return `<tr class="${isFocus ? "focus" : ""} v-${b.virtue}">
            <td><span class="row" style="gap:6px;flex-wrap:nowrap"><span class="key"></span>${esc(b.title)}</span></td>
            ${w.days.map((d) => cell(b.id, d, row[d])).join("")}
            <td><b>${total || ""}</b></td></tr>`;
        }).join("")}</tbody>
      </table>
    </section>`;
  $("#pw").onclick = () => { location.hash = `#/review?start=${addDays(w.start, -7)}`; };
  $("#nw").onclick = () => { location.hash = `#/review?start=${addDays(w.start, 7)}`; };
  $("#tw").onclick = () => { location.hash = "#/review"; };
  $(".franklin").addEventListener("click", async (e) => {
    const td = e.target.closest("td.cell"); if (!td) return;
    const id = +td.dataset.id, d = td.dataset.date;
    const cur = td.dataset.v === "" ? null : +td.dataset.v;
    const next = cur === null ? 0 : cur >= 3 ? 0 : cur + 1;
    await api(`/api/evaluations/${d}`, { method: "PUT", json: { lapses: { [id]: next } } });
    td.outerHTML = cell(id, d, next);
  });
  function cell(id, d, v) {
    const today = d === state.meta.today ? " today" : "";
    const inner = v === undefined || v === null ? "" : v === 0 ? `<span class="ok">·</span>` : `<span class="dots">${"<i></i>".repeat(v)}</span>`;
    return `<td class="cell${today}" data-id="${id}" data-date="${d}" data-v="${v ?? ""}" aria-label="${d}">${inner}</td>`;
  }
}

// ---------- Trends ----------
async function renderTrends(params) {
  const days = +(params.get("days") || state.trendDays);
  state.trendDays = days;
  const t = await api(`/api/trends?days=${days}`);
  const rows = t.days;
  const s = t.summary;
  const labels = rows.map((r) => r.date);
  const avg = (xs) => { const v = xs.filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const recent = rows.slice(-Math.min(30, rows.length));
  const avgSleep = avg(recent.map((r) => r.health.sleep_seconds ? r.health.sleep_seconds / 3600 : null));
  const delta = (o) => o?.delta == null ? `<span class="muted">vs prior half: —</span>` :
    `<span class="${o.delta >= 0 ? "delta-up" : "delta-down"}">${o.delta >= 0 ? "▲" : "▼"} ${Math.abs(o.delta)} pts vs prior ${Math.floor(days / 2)}d</span>`;

  view.innerHTML = `
    <div class="page-head">
      <div><h1>Trends</h1><div class="sub">${esc(fmtDate(t.start, { month: "short", day: "numeric", year: "numeric" }))} – ${esc(fmtDate(t.end, { month: "short", day: "numeric", year: "numeric" }))}</div></div>
      <div class="segmented" role="group" aria-label="Date range">
        ${[30, 90, 180, 365].map((n) => `<button data-d="${n}" class="${n === days ? "on" : ""}">${n === 365 ? "1y" : n + "d"}</button>`).join("")}
      </div>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="label">Virtue adherence</div><div class="value">${s.overall.current == null ? "—" : Math.round(s.overall.current) + "%"}</div><div class="delta">${delta(s.overall)}</div></div>
      <div class="kpi"><div class="label">Review streak</div><div class="value">${s.review_streak} <small class="muted" style="font-size:.9rem">days</small></div><div class="delta muted">evenings examined in a row</div></div>
      <div class="kpi"><div class="label">Sleep, last 30d</div><div class="value">${avgSleep == null ? "—" : avgSleep.toFixed(1) + "h"}</div><div class="delta">${delta(s.rest)}</div></div>
      <div class="kpi"><div class="label">Recovery</div><div class="value">${s.recovery.current == null ? "—" : Math.round(s.recovery.current)}</div><div class="delta">${delta(s.recovery)}</div></div>
    </div>
    <div class="grid two">
      <section class="card span-2"><h2>The four virtues <span class="hint">% of behaviours kept · 7-day average</span></h2>
        ${legend(VIRTUE_ORDER.map((v) => [state.meta.virtues[v].name, css(v), DASHED.has(v)]))}
        <div class="chart-box tall"><canvas id="c-virtues"></canvas></div></section>
      <section class="card span-2"><h2>Daily examination <span class="hint">% kept each day</span></h2>
        <div id="heatmap"></div></section>
      <section class="card span-2"><h2>Balance <span class="hint">philosophy · exercise · rest · recovery, 7-day average</span></h2>
        ${legend(PILLARS.map(([k, l]) => [l, css(k), DASHED.has(k)]))}
        <div class="chart-box tall"><canvas id="c-pillars"></canvas></div></section>
      <section class="card"><h2>Sleep <span class="hint">hours per night</span></h2><div class="chart-box"><canvas id="c-sleep"></canvas></div></section>
      <section class="card"><h2>HRV <span class="hint">ms, overnight average</span></h2><div class="chart-box"><canvas id="c-hrv"></canvas></div></section>
      <section class="card"><h2>Resting heart rate <span class="hint">bpm</span></h2><div class="chart-box"><canvas id="c-rhr"></canvas></div></section>
      <section class="card"><h2>Sleep vs. virtue <span class="hint">each dot a day</span></h2><div class="chart-box"><canvas id="c-scatter"></canvas></div></section>
      <section class="card"><h2>What moves you <span class="hint">correlation, −1 to +1</span></h2>
        <div class="corr">${t.correlations.map((c) => corrRow(c)).join("")}</div>
        <p class="small muted" style="margin-top:10px">Correlation needs at least 7 days with both values. It suggests, it doesn't prove.</p></section>
      <section class="card"><h2>Franklin's tally <span class="hint">lapses per evaluation</span></h2>
        ${legend(VIRTUE_ORDER.map((v) => [state.meta.virtues[v].name, css(v)]), "rect")}
        <div class="chart-box"><canvas id="c-franklin"></canvas></div></section>
      <section class="card span-2"><details><summary>Table view</summary><div class="table-scroll" style="max-height:420px;margin-top:10px">${dataTable(rows)}</div></details></section>
    </div>`;

  $$(".segmented button").forEach((b) => b.onclick = () => { location.hash = `#/trends?days=${b.dataset.d}`; });
  drawHeatmap($("#heatmap"), rows);

  let base = baseOptions();
  const fresh = () => (base = baseOptions());
  const line = (label, data, color, key) => ({ label, data, borderColor: color, backgroundColor: color, borderWidth: 2, borderDash: DASHED.has(key) ? [6, 4] : [], pointRadius: 0, pointHoverRadius: 4, tension: 0.3, spanGaps: true });
  fresh(); state.charts.push(new Chart($("#c-virtues"), {
    type: "line",
    data: { labels: [...labels], datasets: VIRTUE_ORDER.map((v) => line(state.meta.virtues[v].name, rolling(rows.map((r) => r.adherence[v])), css(v), v)) },
    options: pct(base),
  }));
  fresh(); state.charts.push(new Chart($("#c-pillars"), {
    type: "line",
    data: { labels: [...labels], datasets: PILLARS.map(([k, l]) => line(l, rolling(rows.map((r) => r.pillars[k])), css(k), k)) },
    options: pct(base),
  }));
  fresh(); state.charts.push(new Chart($("#c-sleep"), {
    type: "bar",
    data: { labels: [...labels], datasets: [{ label: "Sleep (h)", data: rows.map((r) => r.health.sleep_seconds ? +(r.health.sleep_seconds / 3600).toFixed(2) : null),
      backgroundColor: css("rest"), borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "bottom", categoryPercentage: 0.9, barPercentage: 0.9 }] },
    options: single(base, "h"),
  }));
  fresh(); state.charts.push(new Chart($("#c-hrv"), {
    type: "line", data: { labels: [...labels], datasets: [line("HRV (ms)", rows.map((r) => r.health.hrv_ms), css("justice"))] }, options: single(base, "ms"),
  }));
  fresh(); state.charts.push(new Chart($("#c-rhr"), {
    type: "line", data: { labels: [...labels], datasets: [line("Resting HR", rows.map((r) => r.health.resting_hr), css("courage"))] }, options: single(base, "bpm"),
  }));
  fresh(); state.charts.push(new Chart($("#c-scatter"), {
    type: "scatter",
    data: { datasets: [{ label: "Day", data: rows.filter((r) => r.health.sleep_seconds && r.adherence.overall != null)
      .map((r) => ({ x: +(r.health.sleep_seconds / 3600).toFixed(2), y: r.adherence.overall, date: r.date })),
      backgroundColor: css("wisdom"), borderColor: css("surface"), borderWidth: 2, pointRadius: 5, pointHoverRadius: 7, pointHitRadius: 12 }] },
    options: { ...base, interaction: { mode: "nearest", intersect: false },
      plugins: { ...base.plugins, tooltip: { ...base.plugins.tooltip, callbacks: {
        title: (it) => fmtDate(it[0].raw.date, { month: "short", day: "numeric" }),
        label: (it) => `${it.raw.y}% kept · ${it.raw.x}h sleep` } } },
      scales: { x: { ...base.scales.x, type: "linear", title: { display: true, text: "Sleep (h)", color: css("muted") }, ticks: { ...base.scales.x.ticks, maxTicksLimit: 6 } },
        y: { ...base.scales.y, min: 0, max: 100, ticks: { ...base.scales.y.ticks, callback: (v) => v + "%" } } } },
  }));
  const ft = t.franklin_totals.filter((x) => x.evaluated);
  fresh(); state.charts.push(new Chart($("#c-franklin"), {
    type: "bar",
    data: { labels: ft.map((x) => x.franklin), datasets: [{ label: "Lapses per evaluation", data: ft.map((x) => +(x.lapses / x.evaluated).toFixed(2)),
      backgroundColor: ft.map((x) => css(x.virtue) || css("muted")), borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "left", barPercentage: 0.8 }] },
    options: { ...base, indexAxis: "y", interaction: { mode: "nearest", intersect: true, axis: "y" },
      scales: { x: { ...base.scales.y, beginAtZero: true }, y: { ...base.scales.x, grid: { display: false }, ticks: { ...base.scales.x.ticks, autoSkip: false, maxTicksLimit: 20 } } } },
  }));
}

function legend(items, shape = "line") {
  return `<div class="legend">${items.map(([label, c, dashed]) =>
    `<span><i class="${shape === "line" ? "line" : "key"}${dashed && shape === "line" ? " dashed" : ""}" style="--c:${c};${shape === "rect" ? `background:${c};border-radius:2px;width:10px;height:10px` : ""}"></i>${esc(label)}</span>`).join("")}</div>`;
}
const isISODate = (l) => typeof l === "string" && /^\d{4}-\d{2}-\d{2}$/.test(l);
function baseOptions() {
  const grid = css("grid"), muted = css("muted");
  return {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: css("surface"), titleColor: css("ink-2"), bodyColor: css("ink"), borderColor: css("border") || grid, borderWidth: 1,
        padding: 10, boxWidth: 12, boxHeight: 2, usePointStyle: false, bodyFont: { weight: "600" },
        callbacks: { title: (it) => isISODate(it[0]?.label) ? fmtDate(it[0].label, { weekday: "short", month: "short", day: "numeric" }) : it[0]?.label },
      },
    },
    scales: {
      x: { grid: { display: false }, border: { color: css("axis") }, ticks: { color: muted, maxTicksLimit: 7, maxRotation: 0,
        callback(v) { const l = this.getLabelForValue(v); return isISODate(l) ? fmtDate(l, { month: "short", day: "numeric" }) : l; } } },
      y: { grid: { color: grid }, border: { display: false }, ticks: { color: muted, maxTicksLimit: 5 } },
    },
  };
}
function pct(base) { return { ...base, scales: { ...base.scales, y: { ...base.scales.y, min: 0, max: 100, ticks: { ...base.scales.y.ticks, callback: (v) => v + "%" } } } }; }
function single(base, unit) {
  return { ...base, plugins: { ...base.plugins, tooltip: { ...base.plugins.tooltip, callbacks: { ...base.plugins.tooltip.callbacks, label: (it) => `${it.formattedValue} ${unit}` } } } };
}
function corrRow(c) {
  const r = c.r;
  const fill = r == null ? "" : `<span class="fill" style="background:${r >= 0 ? css("wisdom") : css("recovery")};${r >= 0 ? `left:50%;width:${r * 50}%` : `right:50%;width:${-r * 50}%`}"></span>`;
  return `<span>${esc(c.label)}</span><span class="track" title="n = ${c.n}">${fill}</span><span class="r">${r == null ? `<span class="muted">n=${c.n}</span>` : (r > 0 ? "+" : "") + r.toFixed(2)}</span>`;
}
function drawHeatmap(el, rows) {
  const first = new Date(rows[0].date + "T12:00:00");
  const pad = (first.getDay() + 6) % 7; // Monday-first rows
  const steps = ["seq-1", "seq-2", "seq-3", "seq-4", "seq-5", "seq-6"];
  const color = (v) => v == null ? css("seq-0") : css(steps[Math.min(5, Math.floor(v / 100 * 6 - 1e-9))] ?? "seq-1");
  el.innerHTML = `<div class="heatmap">${"<div class='hc empty'></div>".repeat(pad)}${rows.map((r) =>
    `<div class="hc" tabindex="0" data-d="${r.date}" data-v="${r.adherence.overall ?? ""}" data-l="${r.lapses ?? ""}" style="background:${color(r.adherence.overall)}"></div>`).join("")}</div>
    <div class="heat-legend">Not reviewed <i style="background:${css("seq-0")}"></i><span style="margin-left:8px">0%</span>${steps.map((s) => `<i style="background:${css(s)}"></i>`).join("")}<span>100% kept</span></div>`;
  const tip = $("#tooltip");
  const show = (e) => {
    const c = e.target.closest(".hc[data-d]"); if (!c) return;
    tip.hidden = false;
    tip.innerHTML = `<b>${c.dataset.v === "" ? "Not reviewed" : Math.round(c.dataset.v) + "% kept"}</b><br><span class="muted">${esc(fmtDate(c.dataset.d, { weekday: "short", month: "short", day: "numeric" }))}${c.dataset.l ? ` · ${c.dataset.l} lapses` : ""}</span>`;
    const rect = c.getBoundingClientRect();
    tip.style.left = Math.min(window.innerWidth - 180, rect.left) + "px";
    tip.style.top = rect.top - 52 + "px";
  };
  el.addEventListener("pointermove", show); el.addEventListener("focusin", show);
  el.addEventListener("pointerleave", () => tip.hidden = true); el.addEventListener("focusout", () => tip.hidden = true);
  el.addEventListener("click", (e) => { const c = e.target.closest(".hc[data-d]"); if (c) location.hash = `#/today?date=${c.dataset.d}`; });
}
function dataTable(rows) {
  const cols = [["Date", (r) => r.date], ["Kept %", (r) => n(r.adherence.overall)], ["Lapses", (r) => r.lapses ?? "—"],
    ...VIRTUE_ORDER.map((v) => [state.meta.virtues[v].name, (r) => n(r.adherence[v])]),
    ...PILLARS.map(([k, l]) => [l, (r) => n(r.pillars[k])]),
    ["Sleep h", (r) => hours(r.health.sleep_seconds) ?? "—"], ["HRV", (r) => n(r.health.hrv_ms)], ["RHR", (r) => n(r.health.resting_hr)],
    ["Steps", (r) => r.health.steps ?? "—"], ["Mood", (r) => r.mood ?? "—"]];
  return `<table class="data-table"><thead><tr>${cols.map(([h]) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${
    [...rows].reverse().map((r) => `<tr>${cols.map(([, f]) => `<td>${esc(f(r))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

// ---------- Calendar ----------
async function renderCalendar() {
  view.innerHTML = `<div class="page-head"><div><h1>Calendar</h1><div class="sub">Where this week offers chances to practise</div></div></div><div id="cal" class="card">Loading…</div>`;
  const [c, g] = await Promise.all([api("/api/calendar/opportunities?days=7"), api("/api/google/status")]);
  const box = $("#cal");
  if (!c.connected) {
    box.innerHTML = `<div class="empty-state"><p>Connect Google Calendar to see each meeting, workout and open window as a chance to practise a virtue.</p>
      <p style="margin-top:12px"><a class="btn primary" href="#/settings">Connect in Settings</a></p></div>`;
    return;
  }
  const byDay = {};
  c.events.forEach((e) => (byDay[e.start.slice(0, 10)] ||= { events: [], windows: [] }).events.push(e));
  c.open_windows.forEach((w) => (byDay[w.start.slice(0, 10)] ||= { events: [], windows: [] }).windows.push(w));
  const days = Object.keys(byDay).sort();
  box.innerHTML = days.map((d) => {
    const items = [...byDay[d].events.map((e) => ({ ...e, t: e.start, type: "event" })),
      ...byDay[d].windows.map((w) => ({ ...w, t: w.start, type: "window" }))].sort((a, b) => a.t.localeCompare(b.t));
    return `<div class="day-block"><h3>${esc(fmtDate(d))}</h3>${items.map((i) => i.type === "event" ? `
      <div class="event"><div class="time">${i.all_day ? "All day" : esc(fmtTime(i.start))}</div>
        <div class="body"><div class="row"><b>${esc(i.summary)}</b>${virtueChip(i.virtue)}</div>${i.practice ? `<p>${esc(i.practice)}</p>` : ""}</div></div>` : `
      <div class="event window"><div class="time">${esc(fmtTime(i.start))}</div>
        <div class="body"><b>Open: ${i.minutes} min</b><p>${i.minutes >= 60 ? "Room for a training session, or a long walk to think." : "Room for a walk, mobility, or ten minutes of reading."}</p>
        ${g.write ? `<div class="row" style="margin-top:6px">
          <button class="btn small" data-add="Training" data-s="${i.start}" data-m="${Math.min(i.minutes, 60)}">+ Training block</button>
          <button class="btn small" data-add="Walk & reflect" data-s="${i.start}" data-m="${Math.min(i.minutes, 30)}">+ Walk & reflect</button></div>` : ""}
        </div></div>`).join("")}</div>`;
  }).join("") || `<div class="empty-state">Nothing on the calendar this week.</div>`;
  box.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-add]"); if (!b) return;
    const start = new Date(b.dataset.s), end = new Date(start.getTime() + b.dataset.m * 60000);
    try {
      await api("/api/calendar/block", { json: { summary: `Stoa · ${b.dataset.add}`, description: "Added by Stoa: practise with intention.",
        start: start.toISOString(), end: end.toISOString() } });
      toast("Added to Google Calendar"); renderCalendar();
    } catch (err) { toast(err.message); }
  });
}

// ---------- Settings ----------
async function renderSettings(params) {
  const [gs, gg, behaviors, session] = await Promise.all([api("/api/garmin/status"), api("/api/google/status"), api("/api/behaviors?all=true"), api("/api/session")]);
  if (params.get("google") === "connected") toast("Google Calendar connected");
  if (params.get("google") === "error") toast("Google sign-in failed. Check the redirect URI in README.");
  const theme = localStorageGet("stoa-theme") || "auto";
  view.innerHTML = `
    <div class="page-head"><div><h1>Settings</h1><div class="sub">Connections, behaviours, and your data</div></div></div>
    <div class="grid two">
      <section class="card stack" id="garmin">
        <h2>Garmin Connect ${statusDot(gs.connected && !gs.last_error, gs.last_error)}</h2>
        ${gs.connected ? `<p class="small muted">Syncs automatically 3× a day. Last sync: ${gs.last_sync ? esc(new Date(gs.last_sync).toLocaleString()) : "never"}</p>
          ${gs.last_error ? `<p class="small delta-down">${esc(gs.last_error)}</p>` : ""}
          <div class="row"><button class="btn primary" data-sync="3">Sync now</button><button class="btn" data-sync="30">Backfill 30 days</button>
          <button class="btn" data-sync="180">Backfill 180 days</button><span class="spacer"></span><button class="btn ghost" id="g-off">Disconnect</button></div>`
        : gs.awaiting_mfa ? `<form id="g-mfa" class="stack"><p class="small">Garmin sent you a verification code.</p>
          <input id="g-code" inputmode="numeric" autocomplete="one-time-code" placeholder="123456" required><button class="btn primary">Verify</button></form>`
        : `<p class="small muted">Sign in once. Stoa keeps Garmin's session tokens on your server, not your password, and pulls sleep, HRV, Body Battery, stress, readiness, steps and activities automatically.</p>
          <form id="g-login" class="stack"><input id="g-email" type="email" placeholder="Garmin email" autocomplete="username" required>
          <input id="g-pass" type="password" placeholder="Garmin password" autocomplete="current-password" required>
          <button class="btn primary">Connect Garmin</button></form>`}
      </section>

      <section class="card stack">
        <h2>Google Calendar ${statusDot(gg.connected)}</h2>
        ${!gg.configured ? `<p class="small muted">Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to the server's .env to enable this. The README walks through it in five minutes.</p>`
        : gg.connected ? `<p class="small muted">Connected (${gg.write ? "can add practice blocks" : "read-only"}).</p><div class="row"><a class="btn" href="#/calendar">View opportunities</a><button class="btn ghost" id="cal-off">Disconnect</button></div>`
        : `<p class="small muted">Stoa reads your schedule to find meetings, workouts, and open windows where you can practise.</p><a class="btn primary" href="/api/google/auth">Connect Google Calendar</a>`}
      </section>

      <section class="card stack">
        <h2>Upload health data</h2>
        <p class="small muted">No auto-sync? Upload a Garmin Connect activities CSV export, or a daily CSV with a <code>date</code> column and any of:
          ${state.meta.health_fields.map((f) => `<code>${f}</code>`).join(", ")}.</p>
        <input type="file" id="csv" accept=".csv,text/csv">
      </section>

      <section class="card stack">
        <h2>Log today manually</h2>
        <form id="manual" class="form-grid">
          ${[["sleep_hours", "Sleep (h)"], ["hrv_ms", "HRV (ms)"], ["resting_hr", "Resting HR"], ["steps", "Steps"], ["intensity_minutes", "Intensity min"], ["weight_kg", "Weight (kg)"]]
            .map(([k, l]) => `<div><label for="m-${k}">${l}</label><input id="m-${k}" name="${k}" type="number" step="any" inputmode="decimal"></div>`).join("")}
          <div style="grid-column:1/-1"><button class="btn primary">Save for ${esc(fmtDate(state.meta.today, { month: "short", day: "numeric" }))}</button></div>
        </form>
      </section>

      <section class="card span-2">
        <h2>Behaviours <span class="hint">what you examine each evening</span></h2>
        <div id="beh"></div>
        <form id="beh-new" class="form-grid" style="margin-top:12px">
          <div><label for="bn-v">Virtue</label><select id="bn-v">${VIRTUE_ORDER.map((v) => `<option value="${v}">${state.meta.virtues[v].name}</option>`).join("")}</select></div>
          <div><label for="bn-f">Franklin virtue</label><select id="bn-f"><option value="">—</option>${state.meta.franklin.map((f) => `<option>${f.name}</option>`).join("")}</select></div>
          <div><label for="bn-t">Title</label><input id="bn-t" type="text" required placeholder="Read 20 pages"></div>
          <div style="grid-column:1/-1"><label for="bn-q">Evening question</label><input id="bn-q" type="text" placeholder="Did I read with attention?"></div>
          <div><button class="btn primary">Add behaviour</button></div>
        </form>
      </section>

      <section class="card stack">
        <h2>Your data</h2>
        <p class="small muted">Everything lives in one SQLite file on your server. Export a full backup any time.</p>
        <div class="row"><a class="btn" href="/api/export" download>Export JSON</a>
          <label class="btn" style="margin:0;color:inherit;font-size:inherit">Import JSON<input type="file" id="imp" accept="application/json" hidden></label></div>
      </section>

      <section class="card stack">
        <h2>Appearance</h2>
        <div class="segmented" id="theme">${["auto", "light", "dark"].map((t) => `<button class="${t === theme ? "on" : ""}" data-t="${t}">${t[0].toUpperCase() + t.slice(1)}</button>`).join("")}</div>
        ${session.password_required ? `<div><button class="btn ghost" id="logout">Sign out</button></div>` : `<p class="small delta-down">No STOA_PASSWORD set: anyone who can reach this server can see your data.</p>`}
        <p class="small muted">On iPhone: open in Safari → Share → Add to Home Screen.</p>
      </section>
    </div>`;

  // Garmin
  $("#g-login")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = e.submitter; btn.disabled = true; btn.textContent = "Connecting…";
    try {
      const r = await api("/api/garmin/connect", { json: { email: $("#g-email").value, password: $("#g-pass").value } });
      if (r.status === "ok") { toast("Garmin connected. Pulling 30 days…"); await api("/api/garmin/sync?days=30", { method: "POST" }); }
      renderSettings(new URLSearchParams());
    } catch (err) { toast(err.message); btn.disabled = false; btn.textContent = "Connect Garmin"; }
  });
  $("#g-mfa")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("/api/garmin/mfa", { json: { code: $("#g-code").value } }); toast("Garmin connected. Pulling 30 days…");
      await api("/api/garmin/sync?days=30", { method: "POST" }); renderSettings(new URLSearchParams()); }
    catch (err) { toast(err.message); }
  });
  $$("[data-sync]").forEach((b) => b.onclick = async () => {
    b.disabled = true; const label = b.textContent; b.textContent = "Syncing…";
    try { const r = await api(`/api/garmin/sync?days=${b.dataset.sync}`, { method: "POST" }); toast(`Synced ${r.days.length} days, ${r.activities} activities`); }
    catch (err) { toast(err.message); }
    renderSettings(new URLSearchParams());
  });
  $("#g-off")?.addEventListener("click", async () => { if (confirm("Disconnect Garmin? Your stored data stays.")) { await api("/api/garmin/disconnect", { method: "POST" }); renderSettings(new URLSearchParams()); } });
  $("#cal-off")?.addEventListener("click", async () => { await api("/api/google/disconnect", { method: "POST" }); renderSettings(new URLSearchParams()); });

  // Uploads
  $("#csv").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/upload", { method: "POST", body: fd }); toast(`Imported ${r.rows} ${r.kind} rows`); }
    catch (err) { toast(err.message); }
    e.target.value = "";
  };
  $("#manual").onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries([...new FormData(e.target)].filter(([, v]) => v !== "").map(([k, v]) => [k, +v]));
    if (data.sleep_hours) { data.sleep_seconds = Math.round(data.sleep_hours * 3600); delete data.sleep_hours; }
    await api(`/api/health/${state.meta.today}`, { method: "PUT", json: data });
    toast("Saved"); e.target.reset();
  };
  $("#imp").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try { const r = await api("/api/import", { json: JSON.parse(await f.text()) }); toast(`Imported: ${Object.entries(r).map(([k, v]) => `${v} ${k}`).join(", ")}`); }
    catch (err) { toast(err.message); }
  };

  // Behaviours
  const drawBeh = (list) => {
    $("#beh").innerHTML = VIRTUE_ORDER.map((v) => {
      const items = list.filter((b) => b.virtue === v);
      return items.length ? `<div class="virtue-group"><h3>${virtueChip(v)}</h3>${items.map((b) => `
        <div class="behavior"><div class="q"><b>${esc(b.title)}</b><span>${esc(b.question)}${b.franklin ? ` · <i>${esc(b.franklin)}</i>` : ""}</span></div>
          <label class="small row" style="margin:0;gap:4px"><input type="checkbox" data-active="${b.id}" ${b.active ? "checked" : ""}> active</label>
          <button class="btn ghost icon" data-del="${b.id}" aria-label="Delete ${esc(b.title)}">✕</button></div>`).join("")}</div>` : "";
    }).join("");
  };
  drawBeh(behaviors);
  $("#beh").addEventListener("change", async (e) => {
    const id = e.target.dataset.active; if (!id) return;
    const b = behaviors.find((x) => x.id === +id); b.active = e.target.checked ? 1 : 0;
    await api("/api/behaviors", { json: b });
  });
  $("#beh").addEventListener("click", async (e) => {
    const id = e.target.closest("[data-del]")?.dataset.del; if (!id) return;
    if (!confirm("Delete this behaviour and its history? Untick 'active' instead to keep history.")) return;
    await api(`/api/behaviors/${id}`, { method: "DELETE" });
    drawBeh(await api("/api/behaviors?all=true"));
  });
  $("#beh-new").onsubmit = async (e) => {
    e.preventDefault();
    await api("/api/behaviors", { json: { virtue: $("#bn-v").value, franklin: $("#bn-f").value, title: $("#bn-t").value, question: $("#bn-q").value || $("#bn-t").value } });
    e.target.reset(); const list = await api("/api/behaviors?all=true"); behaviors.splice(0, behaviors.length, ...list); drawBeh(list);
  };

  // Theme / session
  $("#theme").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; setTheme(b.dataset.t); $$("#theme button").forEach((x) => x.classList.toggle("on", x === b)); };
  $("#logout")?.addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); renderLogin(); });
}
function statusDot(ok, bad) {
  return `<span class="status-line hint"><span class="sdot ${bad ? "bad" : ok ? "good" : "off"}"></span>${bad ? "error" : ok ? "connected" : "not connected"}</span>`;
}
function localStorageGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function setTheme(t) {
  try { t === "auto" ? localStorage.removeItem("stoa-theme") : localStorage.setItem("stoa-theme", t); } catch { /* private mode */ }
  if (t === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.dataset.theme = t;
}

// ---------- boot ----------
async function boot() {
  const s = await (await fetch("/api/session", { credentials: "same-origin" })).json();
  if (!s.authenticated) return renderLogin();
  state.meta = await api("/api/meta");
  $(".nav").style.display = "";
  window.onhashchange = route;
  await route();
}
setTheme(localStorageGet("stoa-theme") || "auto");
if (window.Chart) { Chart.defaults.font.family = getComputedStyle(document.body).fontFamily; }
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
// Re-render on theme change so charts pick up the other mode's colours.
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => state.meta && route());
boot();
