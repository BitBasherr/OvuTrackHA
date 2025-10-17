// custom_components/fertility_tracker/frontend/panel.js
// Full-screen sidebar panel available at /fertility-tracker
// Home Assistant will look for <ha-panel-fertility-tracker>.

class HaPanelFertilityTracker extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._inited) {
      this._inited = true;
      this._render();
      this._bootstrap();
    }
  }

  set panel(p) {
    this._panel = p; // panel.config may contain entry_id later if you want
  }

  _render() {
    const root = (this._root = this.attachShadow({ mode: "open" }));
    root.innerHTML = `
      <style>
        :host { display:block; }
        .page {
          max-width: 1100px;
          margin: 0 auto;
          padding: 16px;
        }
        h1 { margin: 0 0 16px; }
        ha-card { display:block; }
        .row { display:flex; gap:12px; flex-wrap: wrap; align-items: center; }
        .grid {
          display:grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 12px;
        }
        label { font-size: 0.9em; color: var(--secondary-text-color); display:block; margin-bottom: 4px; }
        input, textarea, select {
          width: 100%;
          box-sizing: border-box;
          padding: 8px;
          border-radius: 8px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        button {
          padding: 8px 12px;
          border-radius: 8px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          cursor: pointer;
        }
        pre {
          background: var(--card-background-color);
          padding: 12px;
          border-radius: 8px;
          overflow: auto;
          margin: 0;
        }
        .muted { color: var(--secondary-text-color); }
      </style>

      <div class="page">
        <h1>Fertility Tracker</h1>

        <ha-card header="Cycles">
          <div class="card-content">
            <div class="row" style="margin-bottom:12px;">
              <button id="refresh">Refresh</button>
              <span id="entryLabel" class="muted"></span>
            </div>

            <div id="cyclesZone"><em class="muted">Loading…</em></div>
          </div>
        </ha-card>

        <br />

        <ha-card header="Add / Edit Period">
          <div class="card-content">
            <div class="grid">
              <div>
                <label>Start (YYYY-MM-DD)</label>
                <input id="start" placeholder="2025-09-01"/>
              </div>
              <div>
                <label>End (YYYY-MM-DD)</label>
                <input id="end" placeholder="2025-09-05"/>
              </div>
              <div>
                <label>Notes</label>
                <input id="notes" placeholder="optional note"/>
              </div>
              <div>
                <label>Cycle ID (for Edit/Delete)</label>
                <input id="cycle_id" placeholder="cid-..."/>
              </div>
            </div>
            <div class="row" style="margin-top:12px;">
              <button id="add">Add Period</button>
              <button id="edit">Edit Cycle</button>
              <button id="del">Delete Cycle</button>
              <button id="export">Export JSON</button>
            </div>
          </div>
        </ha-card>

        <br />

        <ha-card header="Debug / Export">
          <div class="card-content">
            <pre id="out">—</pre>
          </div>
        </ha-card>
      </div>
    `;

    root.getElementById("refresh").addEventListener("click", () => this._load());
    root.getElementById("add").addEventListener("click", () => this._add());
    root.getElementById("edit").addEventListener("click", () => this._edit());
    root.getElementById("del").addEventListener("click", () => this._del());
    root.getElementById("export").addEventListener("click", () => this._export());
  }

  async _bootstrap() {
    // Determine entry_id to use.
    this._entry_id = this._panel?.config?.entry_id || null;

    if (!this._entry_id) {
      try {
        const res = await this._hass.callWS({ type: "fertility_tracker/list_entries" });
        const ents = res?.entries || [];
        if (ents.length) {
          this._entry_id = ents[0].entry_id; // pick the first for now
          const label = this._root.getElementById("entryLabel");
          label.textContent = `Entry: ${ents[0].title} (${ents[0].entry_id})`;
        }
      } catch (e) {
        this._setOut("Could not discover entries: " + (e?.message || e));
      }
    }
    await this._load();
  }

  _setOut(text) {
    this._root.getElementById("out").textContent = text;
  }

  _cyclesToHtml(data) {
    const cycles = data?.cycles || [];
    if (!cycles.length) return `<em class="muted">No cycles yet.</em>`;
    return `
      <table style="width:100%; border-spacing:0; border-collapse:separate;">
        <thead>
          <tr>
            <th style="text-align:left;">Cycle ID</th>
            <th style="text-align:left;">Start</th>
            <th style="text-align:left;">End</th>
            <th style="text-align:left;">Notes</th>
          </tr>
        </thead>
        <tbody>
          ${cycles.map(c => `
            <tr>
              <td style="padding:6px 8px;"><code>${c.cycle_id}</code></td>
              <td style="padding:6px 8px;">${c.start}</td>
              <td style="padding:6px 8px;">${c.end || "—"}</td>
              <td style="padding:6px 8px;">${c.notes || ""}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  async _load() {
    const zone = this._root.getElementById("cyclesZone");
    if (!this._entry_id) {
      zone.innerHTML = `<em class="muted">No entry configured/found.</em>`;
      return;
    }
    try {
      const data = await this._hass.callWS({
        type: "fertility_tracker/list_cycles",
        entry_id: this._entry_id,
      });
      zone.innerHTML = this._cyclesToHtml(data);
      this._setOut(JSON.stringify(data, null, 2));
    } catch (e) {
      this._setOut("Error loading cycles: " + (e?.message || e));
    }
  }

  async _add() {
    try {
      const start = this._root.getElementById("start").value;
      const end = this._root.getElementById("end").value || undefined;
      const notes = this._root.getElementById("notes").value || undefined;

      await this._hass.callWS({
        type: "fertility_tracker/add_period",
        entry_id: this._entry_id,
        start,
        ...(end ? { end } : {}),
        ...(notes ? { notes } : {}),
      });
      await this._load();
    } catch (e) {
      this._setOut("Add error: " + (e?.message || e));
    }
  }

  async _edit() {
    try {
      const cycle_id = this._root.getElementById("cycle_id").value;
      if (!cycle_id) throw new Error("Cycle ID required for edit");
      const start = this._root.getElementById("start").value || undefined;
      const end = this._root.getElementById("end").value || undefined;
      const notes = this._root.getElementById("notes").value || undefined;

      await this._hass.callWS({
        type: "fertility_tracker/edit_cycle",
        entry_id: this._entry_id,
        cycle_id,
        ...(start ? { start } : {}),
        ...(end ? { end } : {}),
        ...(notes ? { notes } : {}),
      });
      await this._load();
    } catch (e) {
      this._setOut("Edit error: " + (e?.message || e));
    }
  }

  async _del() {
    try {
      const cycle_id = this._root.getElementById("cycle_id").value;
      if (!cycle_id) throw new Error("Cycle ID required for delete");
      await this._hass.callWS({
        type: "fertility_tracker/delete_cycle",
        entry_id: this._entry_id,
        cycle_id,
      });
      await this._load();
    } catch (e) {
      this._setOut("Delete error: " + (e?.message || e));
    }
  }

  async _export() {
    try {
      const data = await this._hass.callWS({
        type: "fertility_tracker/export_data",
        entry_id: this._entry_id,
      });
      this._setOut(JSON.stringify(data, null, 2));
    } catch (e) {
      this._setOut("Export error: " + (e?.message || e));
    }
  }
}

customElements.define("ha-panel-fertility-tracker", HaPanelFertilityTracker);
