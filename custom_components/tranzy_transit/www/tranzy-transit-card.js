/**
 * Tranzy Transit Card - Custom Lovelace card for Home Assistant
 * Displays real-time tram/bus/trolleybus arrivals from Tranzy API
 */

class TranzyTransitCard extends HTMLElement {
  // ─── Card configuration ────────────────────────────────────
  static getConfigElement() {
    return document.createElement("tranzy-transit-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "",
      title: "Transit Arrivals",
      show_header: true,
      show_route_filter: true,
      routes_filter: [],
      max_rows: 10,
      show_realtime_indicator: true,
      compact: false,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._updateCard();
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define an entity (Tranzy Next Arrival sensor)");
    }
    this._config = {
      title: "Transit Arrivals",
      show_header: true,
      show_route_filter: true,
      routes_filter: [],
      max_rows: 10,
      show_realtime_indicator: true,
      compact: false,
      ...config,
    };

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  getCardSize() {
    return this._config?.compact ? 3 : 5;
  }

  _updateCard() {
    if (!this._hass || !this._config) return;

    const entityId = this._config.entity;
    const state = this._hass.states[entityId];

    if (!state) {
      this.shadowRoot.innerHTML = `
        <ha-card>
          <div class="card-content" style="padding:16px;color:var(--error-color);">
            Entity not found: ${entityId}
          </div>
        </ha-card>`;
      return;
    }

    const attrs = state.attributes || {};
    const arrivals = attrs.arrivals || [];
    const routeNames = attrs.route_names || [];
    const stopName = attrs.stop_name || "Transit Stop";
    const routes = attrs.routes || {};

    // Apply route filter
    const selectedRoutes = this._config.routes_filter?.length
      ? this._config.routes_filter
      : routeNames;

    const filteredArrivals = arrivals.filter((a) =>
      selectedRoutes.includes(a.route)
    );

    const displayArrivals = filteredArrivals.slice(0, this._config.max_rows);

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --transit-primary: var(--primary-color, #03a9f4);
          --transit-bg: var(--card-background-color, #1c1c1c);
          --transit-text: var(--primary-text-color, #e1e1e1);
          --transit-secondary: var(--secondary-text-color, #9e9e9e);
          --transit-divider: var(--divider-color, rgba(255,255,255,0.12));
        }

        ha-card {
          background: var(--transit-bg);
          color: var(--transit-text);
          padding: 0;
          overflow: hidden;
        }

        .card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px 8px 16px;
          font-size: 16px;
          font-weight: 500;
        }

        .card-header .stop-name {
          opacity: 0.7;
          font-size: 12px;
          margin-top: 2px;
        }

        .card-header .icon {
          opacity: 0.5;
        }

        .route-filter {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          padding: 0 16px 8px 16px;
        }

        .route-chip {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 32px;
          height: 26px;
          padding: 0 8px;
          border-radius: 13px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
          border: 1px solid var(--transit-divider);
          background: transparent;
          color: var(--transit-secondary);
          user-select: none;
        }

        .route-chip.active {
          background: var(--transit-primary);
          color: #fff;
          border-color: var(--transit-primary);
        }

        .route-chip.tram { --chip-color: #ff9800; }
        .route-chip.bus { --chip-color: #4caf50; }
        .route-chip.trolleybus { --chip-color: #2196f3; }

        .route-chip.active.tram { background: #ff9800; border-color: #ff9800; }
        .route-chip.active.bus { background: #4caf50; border-color: #4caf50; }
        .route-chip.active.trolleybus { background: #2196f3; border-color: #2196f3; }

        .arrivals-list {
          padding: 0;
        }

        .arrival-row {
          display: flex;
          align-items: center;
          padding: 8px 16px;
          border-bottom: 1px solid var(--transit-divider);
          transition: background 0.15s;
        }

        .arrival-row:last-child {
          border-bottom: none;
        }

        .arrival-row:hover {
          background: rgba(255,255,255,0.04);
        }

        .route-badge {
          display: flex;
          align-items: center;
          justify-content: center;
          min-width: 40px;
          height: 28px;
          padding: 0 6px;
          border-radius: 6px;
          font-size: 14px;
          font-weight: 700;
          color: #fff;
          margin-right: 12px;
          flex-shrink: 0;
        }

        .route-badge.tram { background: #ff9800; }
        .route-badge.bus { background: #4caf50; }
        .route-badge.trolleybus { background: #2196f3; }
        .route-badge.metro { background: #9c27b0; }
        .route-badge.rail { background: #795548; }
        .route-badge.unknown { background: #607d8b; }

        .arrival-info {
          flex: 1;
          min-width: 0;
        }

        .arrival-destination {
          font-size: 13px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .arrival-meta {
          font-size: 11px;
          color: var(--transit-secondary);
          margin-top: 1px;
        }

        .arrival-eta {
          text-align: right;
          flex-shrink: 0;
          margin-left: 12px;
        }

        .eta-value {
          font-size: 18px;
          font-weight: 700;
          line-height: 1;
        }

        .eta-value.imminent {
          color: #f44336;
        }

        .eta-value.soon {
          color: #ff9800;
        }

        .eta-value.normal {
          color: #4caf50;
        }

        .eta-unit {
          font-size: 10px;
          color: var(--transit-secondary);
          text-align: right;
        }

        .realtime-dot {
          display: inline-block;
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #4caf50;
          margin-left: 4px;
          animation: pulse 2s infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }

        .no-data {
          padding: 24px 16px;
          text-align: center;
          color: var(--transit-secondary);
          font-size: 14px;
        }

        .no-data .icon {
          font-size: 32px;
          margin-bottom: 8px;
        }

        .compact .arrival-row {
          padding: 4px 16px;
        }

        .compact .eta-value {
          font-size: 15px;
        }

        .compact .route-badge {
          min-width: 34px;
          height: 24px;
          font-size: 12px;
        }
      </style>

      <ha-card class="${this._config.compact ? "compact" : ""}">
        ${
          this._config.show_header
            ? `
          <div class="card-header">
            <div>
              <div>${this._config.title}</div>
              <div class="stop-name">${stopName}</div>
            </div>
            <div class="icon">
              <ha-icon icon="mdi:bus-clock"></ha-icon>
            </div>
          </div>`
            : ""
        }

        ${
          this._config.show_route_filter && routeNames.length > 1
            ? `
          <div class="route-filter">
            ${routeNames
              .map((r) => {
                const routeData = routes[r] || {};
                const type = (routeData.type || "unknown").toLowerCase();
                const isActive = selectedRoutes.includes(r);
                return `<span class="route-chip ${type} ${
                  isActive ? "active" : ""
                }" data-route="${r}">${r}</span>`;
              })
              .join("")}
          </div>`
            : ""
        }

        <div class="arrivals-list">
          ${
            displayArrivals.length === 0
              ? `
            <div class="no-data">
              <div class="icon">🚏</div>
              <div>No upcoming arrivals</div>
            </div>`
              : displayArrivals
                  .map((a) => {
                    const type = (a.type || "unknown").toLowerCase();
                    const eta = a.eta_minutes;
                    let etaClass = "normal";
                    if (eta <= 1) etaClass = "imminent";
                    else if (eta <= 5) etaClass = "soon";

                    const etaText =
                      eta === 0
                        ? "Now"
                        : `${eta}`;
                    const etaUnit = eta === 0 ? "" : "min";

                    return `
                  <div class="arrival-row">
                    <div class="route-badge ${type}">${a.route}</div>
                    <div class="arrival-info">
                      <div class="arrival-destination">${a.destination || ""}</div>
                      <div class="arrival-meta">
                        ${a.type}${a.vehicle_label ? ` · ${a.vehicle_label}` : ""}${
                      a.scheduled ? ` · Sched: ${a.scheduled.substring(0, 5)}` : ""
                    }${
                      this._config.show_realtime_indicator && a.realtime
                        ? '<span class="realtime-dot" title="Real-time data"></span>'
                        : ""
                    }
                      </div>
                    </div>
                    <div class="arrival-eta">
                      <div class="eta-value ${etaClass}">${etaText}</div>
                      <div class="eta-unit">${etaUnit}</div>
                    </div>
                  </div>`;
                  })
                  .join("")
          }
        </div>
      </ha-card>
    `;

    // Attach click handlers for route filter chips
    if (this._config.show_route_filter) {
      this.shadowRoot.querySelectorAll(".route-chip").forEach((chip) => {
        chip.addEventListener("click", (e) => {
          const route = e.target.dataset.route;
          this._toggleRouteFilter(route);
        });
      });
    }
  }

  _toggleRouteFilter(route) {
    if (!this._config) return;

    let currentFilter = [...(this._config.routes_filter || [])];

    if (currentFilter.length === 0) {
      // Nothing selected means all are shown; clicking one means "show only this"
      currentFilter = [route];
    } else if (currentFilter.includes(route)) {
      currentFilter = currentFilter.filter((r) => r !== route);
      // If empty after removal, show all
    } else {
      currentFilter.push(route);
    }

    this._config = { ...this._config, routes_filter: currentFilter };
    this._updateCard();
  }
}

// ─── Card Editor ────────────────────────────────────────────
class TranzyTransitCardEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  _render() {
    if (!this.innerHTML) {
      this.innerHTML = `
        <div style="padding: 16px;">
          <div style="margin-bottom: 12px;">
            <label style="display:block;margin-bottom:4px;font-weight:500;">Entity (Next Arrival sensor)</label>
            <input type="text" id="entity" value="${this._config.entity || ""}"
              style="width:100%;padding:8px;border:1px solid var(--divider-color);border-radius:4px;background:var(--card-background-color);color:var(--primary-text-color);"
              placeholder="sensor.tranzy_..." />
          </div>
          <div style="margin-bottom: 12px;">
            <label style="display:block;margin-bottom:4px;font-weight:500;">Title</label>
            <input type="text" id="title" value="${this._config.title || "Transit Arrivals"}"
              style="width:100%;padding:8px;border:1px solid var(--divider-color);border-radius:4px;background:var(--card-background-color);color:var(--primary-text-color);" />
          </div>
          <div style="margin-bottom: 12px;">
            <label style="display:block;margin-bottom:4px;font-weight:500;">Max rows</label>
            <input type="number" id="max_rows" value="${this._config.max_rows || 10}" min="1" max="30"
              style="width:100px;padding:8px;border:1px solid var(--divider-color);border-radius:4px;background:var(--card-background-color);color:var(--primary-text-color);" />
          </div>
          <div style="margin-bottom: 12px;">
            <label><input type="checkbox" id="show_header" ${this._config.show_header !== false ? "checked" : ""} /> Show header</label>
          </div>
          <div style="margin-bottom: 12px;">
            <label><input type="checkbox" id="show_route_filter" ${this._config.show_route_filter !== false ? "checked" : ""} /> Show route filter chips</label>
          </div>
          <div style="margin-bottom: 12px;">
            <label><input type="checkbox" id="compact" ${this._config.compact ? "checked" : ""} /> Compact mode</label>
          </div>
          <div style="margin-bottom: 12px;">
            <label><input type="checkbox" id="show_realtime_indicator" ${this._config.show_realtime_indicator !== false ? "checked" : ""} /> Show real-time indicator</label>
          </div>
        </div>
      `;

      // Attach change handlers
      ["entity", "title", "max_rows"].forEach((field) => {
        this.querySelector(`#${field}`).addEventListener("input", (e) => {
          const val = field === "max_rows" ? parseInt(e.target.value, 10) : e.target.value;
          this._config = { ...this._config, [field]: val };
          this._dispatch();
        });
      });

      ["show_header", "show_route_filter", "compact", "show_realtime_indicator"].forEach((field) => {
        this.querySelector(`#${field}`).addEventListener("change", (e) => {
          this._config = { ...this._config, [field]: e.target.checked };
          this._dispatch();
        });
      });
    }
  }

  _dispatch() {
    const event = new CustomEvent("config-changed", {
      detail: { config: this._config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}

// ─── Register ────────────────────────────────────────────────
customElements.define("tranzy-transit-card", TranzyTransitCard);
customElements.define("tranzy-transit-card-editor", TranzyTransitCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "tranzy-transit-card",
  name: "Tranzy Transit Card",
  description: "Shows real-time transit arrivals from Tranzy API",
  preview: true,
  documentationURL: "https://github.com/ovi/ha-tranzy-transit",
});

console.info(
  "%c TRANZY-TRANSIT-CARD %c v1.0.0 ",
  "color: white; background: #ff9800; font-weight: bold; padding: 2px 6px; border-radius: 4px 0 0 4px;",
  "color: #ff9800; background: #fff3e0; font-weight: bold; padding: 2px 6px; border-radius: 0 4px 4px 0;"
);
