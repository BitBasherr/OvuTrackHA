// Full-screen panel that embeds the same ft-card UI.
// Loaded by async_register_built_in_panel(module_url=...).

import "/fertility_tracker_frontend/ft-card.js";

class HaPanelFertilityTracker extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (this._card) {
      this._card.hass = hass;
    }
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._card) this._card.narrow = narrow;
  }

  set panel(panel) {
    this._panel = panel;
    // Create once
    if (!this._wrapper) {
      const root = this.attachShadow({ mode: "open" });
      const style = document.createElement("style");
      style.textContent = `
        :host{display:block;height:100%}
        main{height:100%;padding:16px;box-sizing:border-box}
        fertility-tracker-card{display:block;max-width:900px;margin:0 auto}
      `;
      root.appendChild(style);
      const main = document.createElement("main");
      root.appendChild(main);

      this._card = document.createElement("fertility-tracker-card");
      // optional config passthrough (title, entry_id)
      const cfg = {};
      if (panel?.config?.title) cfg.title = panel.config.title;
      if (panel?.config?.entry_id) cfg.entry_id = panel.config.entry_id;
      this._card.setConfig(cfg);

      main.appendChild(this._card);

      this._wrapper = main;
    }
  }

  connectedCallback() {}
  disconnectedCallback() {}
}

customElements.define("ha-panel-fertility-tracker", HaPanelFertilityTracker);
