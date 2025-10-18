// Fertility Tracker Lovelace card (no build step)
// Resource URL: /local/fertility_tracker/ft-card.js  (or your static path)
// Card type: custom:fertility-tracker-card

(function () {
  // Avoid double-define on hot reloads
  if (customElements.get("fertility-tracker-card")) {
    // already registered
    return;
  }

  const css = `
  .ft-card{padding:16px}
  .ft-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;align-items:center}
  .ft-row > *{flex:0 0 auto}
  .ft-actions{margin-top:8px;display:flex;gap:8px;flex-wrap:wrap}
  .ft-hint{opacity:.7;font-size:.9em}
  input[type="date"],input[type="text"],select{padding:4px 6px;border:1px solid var(--divider-color,#4444);border-radius:6px;background:var(--card-background-color);color:var(--primary-text-color)}
  button{padding:6px 10px;border-radius:8px;border:1px solid var(--divider-color,#4444);background:var(--primary-color);color:var(--text-primary-color,#fff);cursor:pointer}
  button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color)}
  button.toggle{padding:4px 8px}
  button[aria-pressed="true"]{outline:2px solid var(--primary-color)}
  .danger{border-color:var(--error-color, #c62828);color:var(--error-color, #c62828);background:transparent}

  /* Editor table */
  .ft-table{width:100%;border-collapse:collapse;margin-top:8px}
  .ft-table th,.ft-table td{border-bottom:1px solid var(--divider-color,#4444);padding:6px 4px;text-align:left}

  /* Month grid */
  .ft-month-wrap{margin-top:4px}
  .ft-month-header{display:flex;justify-content:space-between;align-items:center;margin:8px 0}
  .ft-month-title{font-weight:600}
  .ft-dow{display:grid;grid-template-columns:repeat(7, 1fr);gap:4px;margin-bottom:4px;opacity:.7;font-size:.86em}
  .ft-dow div{text-align:center}
  .ft-month{display:grid;grid-template-columns:repeat(7, 1fr);gap:4px}
  .ft-day{position:relative;min-height:72px;border:1px solid var(--divider-color,#4444);border-radius:8px;padding:6px;background:var(--ha-card-background, var(--card-background-color));}
  .ft-day.muted{opacity:.5}
  .ft-day-num{font-size:.9em;opacity:.9}
  .ft-period{background:
    linear-gradient(0deg, rgba(244,67,54,0.18), rgba(244,67,54,0.18));
    border-color: rgba(244,67,54,0.35);
  }
  .ft-droplets{position:absolute;right:6px;bottom:6px;display:flex;gap:4px}
  .ft-drop{width:14px;height:14px;display:inline-block}
  .ft-drop svg{width:100%;height:100%;display:block;filter:drop-shadow(0 0 2px rgba(0,0,0,.45))}
  .ft-legend{display:flex;gap:14px;align-items:center;margin-top:8px;opacity:.8;font-size:.9em}
  .ft-pill{display:inline-block;width:14px;height:14px;border-radius:4px;background:rgba(244,67,54,0.28);border:1px solid rgba(244,67,54,0.45)}
  `;

  function todayLocalYMD() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function ymd(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function parseYMD(s) {
    // Treat as local midnight
    const [Y, M, D] = s.split("-").map(Number);
    return new Date(Y, M - 1, D);
  }

  function ymdShift(ymdStr, days) {
    if (!ymdStr) return ymdStr;
    const dt = parseYMD(ymdStr);
    dt.setDate(dt.getDate() + days);
    return ymd(dt);
  }

  function inRange(d, startYMD, endYMD) {
    if (!startYMD) return false;
    const s = parseYMD(startYMD);
    const e = endYMD ? parseYMD(endYMD) : s; // open-ended: treat as 1 day
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    return x >= s && x <= e;
  }

  // Small white droplet SVG (currentColor -> white)
  function dropletSVG() {
    return `
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 2c-2.6 3.9-6 7.7-6 12a6 6 0 0012 0c0-4.3-3.4-8.1-6-12z"></path>
      </svg>
    `;
  }

  class FertilityTrackerCard extends HTMLElement {
    static getConfigElement() { return null; }
    static getStubConfig() { return {}; }

    setConfig(config) {
      this._config = config || {};
      if (!this._root) {
        const shadow = this.attachShadow({ mode: "open" });
        const style = document.createElement("style");
        style.textContent = css;
        shadow.appendChild(style);
        this._root = document.createElement("ha-card");
        shadow.appendChild(this._root);
      }
      // default to calendar view
      if (!this._mode) this._mode = "calendar"; // "calendar" | "editor"
      if (this._monthOffset == null) this._monthOffset = 0;
      this._render();
    }

    getCardSize() { return 7; }

    set hass(hass) {
      this._hass = hass;
      if (!this._initDone) {
        this._initDone = true;
        this._bootstrap();
      }
    }

    async _bootstrap() {
      this._entryId = this._config.entry_id || null;
      // Auto-pick first fertility_tracker entry if not provided
      if (!this._entryId) {
        try {
          const entries = await this._hass.callWS({ type: "config_entries/get_entries" });
          const match = entries.find((e) => e.domain === "fertility_tracker");
          if (match) this._entryId = match.entry_id;
        } catch (e) {}
      }
      await this._refresh();
    }

    async _refresh() {
      this._loading = true;
      this._render();
      if (!this._entryId) {
        this._data = null;
        this._loading = false;
        this._render();
        return;
      }
      try {
        this._data = await this._hass.callWS({
          type: "fertility_tracker/list_cycles",
          entry_id: this._entryId,
        });
      } catch (e) {
        this._data = null;
      }
      this._loading = false;
      this._render();
    }

    async _addPeriod(start, end, notes) {
      if (!this._entryId || !start) return;
      await this._hass.callWS({
        type: "fertility_tracker/add_period",
        entry_id: this._entryId,
        start, end, notes,
      });
      await this._refresh();
    }

    async _editCycle(cycleId, start, end, notes) {
      await this._hass.callWS({
        type: "fertility_tracker/edit_cycle",
        entry_id: this._entryId,
        cycle_id: cycleId,
        ...(start ? { start } : {}),
        ...(end ? { end } : {}),
        ...(notes != null ? { notes } : {}),
      });
      await this._refresh();
    }

    async _deleteCycle(cycleId) {
      if (!confirm("Delete this cycle?")) return;
      await this._hass.callWS({
        type: "fertility_tracker/delete_cycle",
        entry_id: this._entryId,
        cycle_id: cycleId,
      });
      await this._refresh();
    }

    // Services
    async _logSex(protectedFlag, note) {
      if (!this._entryId) return;
      await this._hass.callService("fertility_tracker", "log_sex", {
        entry_id: this._entryId,
        protected: !!protectedFlag,
        ...(note ? { notes: note } : {}),
      });
      await this._refresh();
    }

    // Presets
    async _presetAddTodayFixed(days = 5) {
      const start = todayLocalYMD();
      const end = ymdShift(start, days - 1);
      await this._addPeriod(start, end, `Preset ${days}d`);
    }
    async _presetStartToday() {
      await this._addPeriod(todayLocalYMD(), undefined, "Started today");
    }
    async _presetEndLastToday() {
      const last = this._lastCycle();
      if (!last) return;
      await this._editCycle(last.id, null, todayLocalYMD(), last.notes || "");
    }
    async _presetShiftLastStart(delta) {
      const last = this._lastCycle();
      if (!last || !last.start) return;
      await this._editCycle(last.id, ymdShift(last.start, delta), last.end || null, last.notes || "");
    }
    _lastCycle() {
      const c = this._data?.cycles || [];
      if (!c.length) return null;
      return c[c.length - 1];
    }

    // ---------- Calendar helpers ----------
    _monthContext() {
      const base = new Date();
      const cur = new Date(base.getFullYear(), base.getMonth() + this._monthOffset, 1);
      const year = cur.getFullYear();
      const month = cur.getMonth(); // 0-11
      const startDow = new Date(year, month, 1).getDay(); // 0=Sun
      // Start from the Sunday before (or same day if Sunday)
      const calStart = new Date(year, month, 1 - startDow);
      const days = [];
      for (let i = 0; i < 42; i++) {
        const d = new Date(calStart);
        d.setDate(calStart.getDate() + i);
        days.push(d);
      }
      return { year, month, days };
    }

    _isPeriodDay(dateObj) {
      const cycles = this._data?.cycles || [];
      for (const c of cycles) {
        if (inRange(dateObj, c.start, c.end)) return true;
      }
      return false;
    }

    _sexEventsByDay() {
      const map = new Map(); // ymd -> array of events
      const events = this._data?.sex_events || [];
      for (const ev of events) {
        // ev.ts is ISO; take local date
        const d = new Date(ev.ts);
        const key = ymd(new Date(d.getFullYear(), d.getMonth(), d.getDate()));
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(ev);
      }
      return map;
    }

    // ---------- Rendering ----------
    _render() {
      if (!this._root) return;
      const title = this._config.title || "Fertility Tracker";
      const entryStr = this._entryId ? ` · entry_id=${this._entryId}` : "";
      let body = `<div class="ft-card">
        <div class="ft-row">
          <div><b>${title}</b><span class="ft-hint">${entryStr}</span></div>
          <button id="ft-refresh">Refresh</button>
          <span class="ft-hint" style="flex:1 1 auto"></span>
          <button class="toggle" id="ft-mode-cal" aria-pressed="${this._mode==='calendar'}">Calendar</button>
          <button class="toggle" id="ft-mode-ed" aria-pressed="${this._mode==='editor'}">Editor</button>
        </div>
      `;

      if (this._loading) {
        body += `<div>Loading…</div></div>`;
        this._root.innerHTML = body;
        this._wireBasics();
        return;
      }

      if (!this._entryId) {
        body += `<div>No <code>fertility_tracker</code> entry found. Create one in “Devices & Services”.</div></div>`;
        this._root.innerHTML = body;
        this._wireBasics();
        return;
      }

      // Choose view
      if (this._mode === "calendar") {
        body += this._renderCalendar();
      } else {
        body += this._renderEditor();
      }

      body += `</div>`;
      this._root.innerHTML = body;

      // list of wires
      this._wireBasics();
      if (this._mode === "calendar") this._wireCalendar();
      else this._wireEditor();
    }

    _wireBasics() {
      this._root.querySelector("#ft-refresh")?.addEventListener("click", () => this._refresh());
      this._root.querySelector("#ft-mode-cal")?.addEventListener("click", () => { this._mode="calendar"; this._render(); });
      this._root.querySelector("#ft-mode-ed")?.addEventListener("click", () => { this._mode="editor"; this._render(); });
    }

    // ----- Calendar view -----
    _renderCalendar() {
      const { year, month, days } = this._monthContext();
      const monthName = new Date(year, month, 1).toLocaleString(undefined, { month: "long", year: "numeric" });
      const sexMap = this._sexEventsByDay();

      const dow = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
      let html = `
        <div class="ft-month-wrap">
          <div class="ft-month-header">
            <button class="secondary" id="ft-prev">&lt;</button>
            <div class="ft-month-title">${monthName}</div>
            <button class="secondary" id="ft-next">&gt;</button>
          </div>
          <div class="ft-dow">${dow.map(d=>`<div>${d}</div>`).join("")}</div>
          <div class="ft-month">
      `;

      for (const d of days) {
        const isThisMonth = d.getMonth() === month;
        const cls = ["ft-day", isThisMonth ? "" : "muted", this._isPeriodDay(d) ? "ft-period" : ""].join(" ");
        const key = ymd(d);
        const drops = sexMap.get(key) || [];
        html += `<div class="${cls}" data-date="${key}">
          <div class="ft-day-num">${d.getDate()}</div>
          ${drops.length ? `<div class="ft-droplets">${this._renderDroplets(drops)}</div>` : ""}
        </div>`;
      }

      html += `</div>
        <div class="ft-legend">
          <span class="ft-pill"></span> Period day
          <span style="display:inline-flex;align-items:center;gap:6px">
            <span class="ft-drop">${dropletSVG()}</span> Sex logged
          </span>
        </div>
      </div>`;
      return html;
    }

    _renderDroplets(drops) {
      // Always white droplets; show up to 3, then +n
      const shown = drops.slice(0, 3).map(() => `<span class="ft-drop" style="color:#fff">${dropletSVG()}</span>`).join("");
      const extra = drops.length > 3 ? `<span class="ft-hint">+${drops.length-3}</span>` : "";
      return shown + extra;
    }

    _wireCalendar() {
      this._root.querySelector("#ft-prev")?.addEventListener("click", () => { this._monthOffset -= 1; this._render(); });
      this._root.querySelector("#ft-next")?.addEventListener("click", () => { this._monthOffset += 1; this._render(); });
      // Day click? Optional: quick-add start/end, or show popup — skipped to keep it simple.
    }

    // ----- Editor view (your existing UI) -----
    _renderEditor() {
      const cycles = (this._data?.cycles || []).slice();

      const presets = `
        <div class="ft-actions">
          <button id="ft-preset-s5">Add 5-day period (start today)</button>
          <button id="ft-preset-s4">Add 4-day period</button>
          <button id="ft-preset-start">Start period today</button>
          <button id="ft-preset-end">End last period today</button>
          <button id="ft-shift--1">Shift last start −1d</button>
          <button id="ft-shift-+1">Shift last start +1d</button>
        </div>
      `;

      const sex = `
        <div class="ft-actions">
          <button id="ft-sex-unprotected">Log sex (unprotected)</button>
          <button id="ft-sex-protected">Log sex (protected)</button>
          <input id="ft-sex-note" type="text" placeholder="note (optional)">
        </div>
      `;

      const manual = `
        <div class="ft-row">
          <input type="date" id="ft-add-start" value="${todayLocalYMD()}">
          <input type="date" id="ft-add-end" placeholder="end (optional)">
          <input type="text" id="ft-add-notes" placeholder="notes (optional)">
          <button id="ft-add">Add/Save</button>
        </div>
      `;

      let rows = `
        <table class="ft-table">
          <thead><tr><th>Start</th><th>End</th><th>Notes</th><th></th></tr></thead>
          <tbody>
      `;
      for (const c of cycles) {
        const start = c.start || "";
        const end = c.end || "";
        const notes = c.notes || "";
        rows += `
          <tr data-id="${c.id}">
            <td><input type="date" class="ft-start" value="${start}"></td>
            <td><input type="date" class="ft-end" value="${end}"></td>
            <td><input type="text" class="ft-notes" value="${notes.replace(/"/g, "&quot;")}"></td>
            <td>
              <button class="ft-save">Save</button>
              <button class="ft-del danger">Delete</button>
            </td>
          </tr>
        `;
      }
      rows += `</tbody></table>`;

      return presets + sex + manual + rows;
    }

    _wireEditor() {
      this._root.querySelector("#ft-preset-s5")?.addEventListener("click", () => this._presetAddTodayFixed(5));
      this._root.querySelector("#ft-preset-s4")?.addEventListener("click", () => this._presetAddTodayFixed(4));
      this._root.querySelector("#ft-preset-start")?.addEventListener("click", () => this._presetStartToday());
      this._root.querySelector("#ft-preset-end")?.addEventListener("click", () => this._presetEndLastToday());
      this._root.querySelector("#ft-shift--1")?.addEventListener("click", () => this._presetShiftLastStart(-1));
      this._root.querySelector("#ft-shift-+1")?.addEventListener("click", () => this._presetShiftLastStart(+1));

      this._root.querySelector("#ft-add")?.addEventListener("click", async () => {
        const start = this._root.querySelector("#ft-add-start").value || null;
        const end = this._root.querySelector("#ft-add-end").value || null;
        const notes = this._root.querySelector("#ft-add-notes").value || null;
        if (!start) return alert("Start date is required");
        await this._addPeriod(start, end || undefined, notes || undefined);
      });

      this._root.querySelector("#ft-sex-unprotected")?.addEventListener("click", async () => {
        const note = this._root.querySelector("#ft-sex-note").value || "";
        await this._logSex(false, note);
        this._root.querySelector("#ft-sex-note").value = "";
      });
      this._root.querySelector("#ft-sex-protected")?.addEventListener("click", async () => {
        const note = this._root.querySelector("#ft-sex-note").value || "";
        await this._logSex(true, note);
        this._root.querySelector("#ft-sex-note").value = "";
      });

      this._root.querySelectorAll("tr[data-id]").forEach((row) => {
        const id = row.getAttribute("data-id");
        row.querySelector(".ft-save")?.addEventListener("click", async () => {
          const start = row.querySelector(".ft-start").value || null;
          const end = row.querySelector(".ft-end").value || null;
          const notes = row.querySelector(".ft-notes").value ?? null;
          await this._editCycle(id, start || null, end || null, notes ?? null);
        });
        row.querySelector(".ft-del")?.addEventListener("click", async () => {
          await this._deleteCycle(id);
        });
      });
    }
  }

  customElements.define("fertility-tracker-card", FertilityTrackerCard);

  // Make it show up in “+ Add Card → By URL”
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "fertility-tracker-card",
    name: "Fertility Tracker",
    description: "Monthly calendar + quick editor for the Fertility Tracker.",
  });
})();