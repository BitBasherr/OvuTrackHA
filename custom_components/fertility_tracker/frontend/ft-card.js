// Fertility Tracker Lovelace card (no build step)
// Resource URL: /fertility_tracker_frontend/ft-card.js
// Card type: custom:fertility-tracker-card

(function () {
  const css = `
  .ft-card{padding:16px}
  .ft-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}
  .ft-row > *{flex:0 0 auto}
  .ft-table{width:100%;border-collapse:collapse;margin-top:8px}
  .ft-table th,.ft-table td{border-bottom:1px solid var(--divider-color, #ddd);padding:6px 4px;text-align:left}
  .ft-actions{margin-top:8px;display:flex;gap:8px;flex-wrap:wrap}
  .ft-hint{opacity:.7;font-size:.9em}
  input[type="date"],input[type="text"],select{padding:4px 6px;border:1px solid var(--divider-color,#ddd);border-radius:6px;background:var(--card-background-color)}
  button{padding:6px 10px;border-radius:8px;border:1px solid var(--divider-color,#ddd);background:var(--primary-background-color);cursor:pointer}
  button:hover{filter:brightness(0.98)}
  .danger{border-color:var(--error-color, #c62828);color:var(--error-color, #c62828)}
  `;

  function todayLocalYMD() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function ymdShift(ymd, days) {
    if (!ymd) return ymd;
    const [y, m, d] = ymd.split("-").map(Number);
    const dt = new Date(y, m - 1, d);
    dt.setDate(dt.getDate() + days);
    const yy = dt.getFullYear();
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    const dd = String(dt.getDate()).padStart(2, "0");
    return `${yy}-${mm}-${dd}`;
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
      this._render();
    }

    getCardSize() { return 6; }

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

    _render() {
      if (!this._root) return;
      const title = this._config.title || "Fertility Tracker";
      const entryStr = this._entryId ? ` · entry_id=${this._entryId}` : "";
      let body = `<div class="ft-card">
        <div class="ft-row">
          <div><b>${title}</b><span class="ft-hint">${entryStr}</span></div>
          <button id="ft-refresh">Refresh</button>
        </div>
      `;

      if (this._loading) {
        body += `<div>Loading…</div></div>`;
        this._root.innerHTML = body;
        this._root.querySelector("#ft-refresh")?.addEventListener("click", () => this._refresh());
        return;
      }

      if (!this._entryId) {
        body += `<div>No <code>fertility_tracker</code> entry found. Create one in “Devices & Services”.</div></div>`;
        this._root.innerHTML = body;
        this._root.querySelector("#ft-refresh")?.addEventListener("click", () => this._refresh());
        return;
      }

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
            <td><input type="text" class="ft-notes" value="${notes}"></td>
            <td>
              <button class="ft-save">Save</button>
              <button class="ft-del danger">Delete</button>
            </td>
          </tr>
        `;
      }
      rows += `</tbody></table>`;

      body += presets + sex + manual + rows + `</div>`;
      this._root.innerHTML = body;

      // Wire buttons
      this._root.querySelector("#ft-refresh")?.addEventListener("click", () => this._refresh());
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

  // So it shows up in “+ Add Card → By URL”
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "fertility-tracker-card",
    name: "Fertility Tracker",
    description: "Quickly add/edit cycles; updates the Fertility Tracker calendar.",
  });
})();
