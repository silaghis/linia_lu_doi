/**
 * Tranzy Transit Card v3 — hybrid ETA minutes + stops away
 */
class TranzyTransitCard extends HTMLElement {
  static getConfigElement() { return document.createElement("tranzy-transit-card-editor"); }
  static getStubConfig() { return { entity: "", title: "Transit Arrivals", show_route_filter: true, routes_filter: [], max_rows: 10, compact: false }; }

  set hass(h) { this._hass = h; this._render(); }
  setConfig(c) {
    if (!c.entity) throw new Error("Define entity");
    this._config = { title: "Transit Arrivals", show_route_filter: true, routes_filter: [], max_rows: 10, compact: false, ...c };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
  }
  getCardSize() { return this._config?.compact ? 3 : 5; }

  _render() {
    if (!this._hass || !this._config) return;
    const st = this._hass.states[this._config.entity];
    if (!st) { this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px;color:var(--error-color)">Entity not found: ${this._config.entity}</div></ha-card>`; return; }

    const a = st.attributes || {};
    const arrivals = a.arrivals || [];
    const routeNames = a.route_names || [];
    const stopName = a.stop_name || "Transit Stop";
    const routes = a.routes || {};
    const sel = this._config.routes_filter?.length ? this._config.routes_filter : routeNames;
    const filtered = arrivals.filter(x => sel.includes(x.route)).slice(0, this._config.max_rows);

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding:0; overflow:hidden; }
        .hdr { display:flex; align-items:center; justify-content:space-between; padding:12px 16px 6px; }
        .hdr .t { font-size:16px; font-weight:500; }
        .hdr .s { font-size:12px; opacity:.6; margin-top:2px; }
        .chips { display:flex; flex-wrap:wrap; gap:5px; padding:0 16px 8px; }
        .chip { display:inline-flex; align-items:center; justify-content:center; min-width:30px; height:24px; padding:0 8px; border-radius:12px; font-size:12px; font-weight:600; cursor:pointer; border:1px solid var(--divider-color,rgba(255,255,255,.12)); background:transparent; color:var(--secondary-text-color); user-select:none; transition:all .2s; }
        .chip.on { color:#fff; }
        .chip.on.tram { background:#ff9800; border-color:#ff9800; }
        .chip.on.bus { background:#4caf50; border-color:#4caf50; }
        .chip.on.trolleybus { background:#2196f3; border-color:#2196f3; }
        .chip.on.metro { background:#9c27b0; border-color:#9c27b0; }
        .chip.on.other { background:#607d8b; border-color:#607d8b; }
        .rows { padding:0; }
        .row { display:flex; align-items:center; padding:8px 16px; border-bottom:1px solid var(--divider-color,rgba(255,255,255,.12)); }
        .row:last-child { border-bottom:none; }
        .badge { display:flex; align-items:center; justify-content:center; min-width:38px; height:26px; padding:0 6px; border-radius:6px; font-size:13px; font-weight:700; color:#fff; margin-right:12px; flex-shrink:0; }
        .badge.tram { background:#ff9800; }
        .badge.bus { background:#4caf50; }
        .badge.trolleybus { background:#2196f3; }
        .badge.metro { background:#9c27b0; }
        .badge.other { background:#607d8b; }
        .info { flex:1; min-width:0; }
        .dest { font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .meta { font-size:11px; color:var(--secondary-text-color); margin-top:1px; }
        .eta { text-align:right; flex-shrink:0; margin-left:12px; min-width:50px; }
        .eta .v { font-size:20px; font-weight:700; line-height:1; }
        .eta .v.imm { color:#f44336; }
        .eta .v.soon { color:#ff9800; }
        .eta .v.ok { color:#4caf50; }
        .eta .v.unk { color:var(--secondary-text-color); font-size:14px; }
        .eta .u { font-size:10px; color:var(--secondary-text-color); }
        .rt { display:inline-block; width:6px; height:6px; border-radius:50%; background:#4caf50; margin-left:4px; animation:pulse 2s infinite; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        .empty { padding:24px 16px; text-align:center; color:var(--secondary-text-color); font-size:14px; }
        .compact .row { padding:5px 16px; }
        .compact .eta .v { font-size:16px; }
        .compact .badge { min-width:32px; height:22px; font-size:11px; }
      </style>
      <ha-card class="${this._config.compact?'compact':''}">
        <div class="hdr">
          <div><div class="t">${this._config.title}</div><div class="s">${stopName}</div></div>
          <ha-icon icon="mdi:tram" style="opacity:.4"></ha-icon>
        </div>
        ${this._config.show_route_filter && routeNames.length > 1 ? `<div class="chips">${routeNames.map(r => {
          const rd = routes[r]||{};
          const tc = this._tc(rd.type);
          return `<span class="chip ${tc} ${sel.includes(r)?'on':''}" data-r="${r}">${r}</span>`;
        }).join('')}</div>` : ''}
        <div class="rows">
          ${filtered.length === 0 ? '<div class="empty">🚏 No upcoming arrivals</div>' :
            filtered.map(x => {
              const tc = this._tc(x.type);
              let txt, unit, cls;

              // Prefer eta_minutes, fall back to stops_away
              if (x.eta_minutes !== null && x.eta_minutes !== undefined) {
                const m = x.eta_minutes;
                if (m === 0) { txt='Now'; unit=''; cls='imm'; }
                else if (m <= 2) { txt=m; unit='min'; cls='imm'; }
                else if (m <= 5) { txt=m; unit='min'; cls='soon'; }
                else { txt=m; unit='min'; cls='ok'; }
              } else if (x.stops_away !== null && x.stops_away !== undefined) {
                const s = x.stops_away;
                if (s === 0) { txt='HERE'; unit=''; cls='imm'; }
                else if (s <= 2) { txt=s; unit=s===1?'stop':'stops'; cls='imm'; }
                else if (s <= 5) { txt=s; unit='stops'; cls='soon'; }
                else { txt=s; unit='stops'; cls='ok'; }
              } else {
                txt='—'; unit='on route'; cls='unk';
              }

              const sched = x.scheduled_time ? x.scheduled_time.substring(0,5) : '';
              const metaParts = [x.type];
              if (x.vehicle_label) metaParts.push(x.vehicle_label);
              if (sched) metaParts.push('⏱ ' + sched);
              if (x.speed && x.speed > 0) metaParts.push(x.speed + ' km/h');

              return `<div class="row">
                <div class="badge ${tc}">${x.route}</div>
                <div class="info">
                  <div class="dest">${x.destination || x.type || ''}</div>
                  <div class="meta">${metaParts.join(' · ')}${x.realtime?'<span class="rt" title="Live GPS"></span>':''}</div>
                </div>
                <div class="eta">
                  <div class="v ${cls}">${txt}</div>
                  <div class="u">${unit}</div>
                </div>
              </div>`;
            }).join('')}
        </div>
      </ha-card>`;

    this.shadowRoot.querySelectorAll('.chip').forEach(c =>
      c.addEventListener('click', e => this._toggle(e.target.dataset.r))
    );
  }

  _tc(type) {
    if (!type) return 'other';
    const t = type.toLowerCase();
    if (t.includes('tram')) return 'tram';
    if (t === 'bus') return 'bus';
    if (t.includes('trolley')) return 'trolleybus';
    if (t.includes('metro')) return 'metro';
    return 'other';
  }

  _toggle(r) {
    let f = [...(this._config.routes_filter||[])];
    if (!f.length) f = [r];
    else if (f.includes(r)) f = f.filter(x=>x!==r);
    else f.push(r);
    this._config = {...this._config, routes_filter: f};
    this._render();
  }
}

class TranzyTransitCardEditor extends HTMLElement {
  set hass(h) { this._hass = h; }
  setConfig(c) { this._config = c; this._draw(); }
  _draw() {
    if (this.innerHTML) return;
    this.innerHTML = `<div style="padding:16px">
      <p><b>Entity</b> (Next Arrival sensor):</p>
      <input id="e" value="${this._config.entity||''}" style="width:100%;padding:8px;margin-bottom:12px;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:4px" placeholder="sensor.tranzy_...">
      <p><b>Title</b>:</p>
      <input id="t" value="${this._config.title||'Transit Arrivals'}" style="width:100%;padding:8px;margin-bottom:12px;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:4px">
      <p><b>Max rows</b>:</p>
      <input id="m" type="number" value="${this._config.max_rows||10}" min="1" max="30" style="width:80px;padding:8px;margin-bottom:12px;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:4px">
      <div style="margin:8px 0"><label><input type="checkbox" id="f" ${this._config.show_route_filter!==false?'checked':''}> Show route filter chips</label></div>
      <div style="margin:8px 0"><label><input type="checkbox" id="c" ${this._config.compact?'checked':''}> Compact mode</label></div>
    </div>`;
    ['e','t','m'].forEach(id => this.querySelector('#'+id).addEventListener('input', ()=>this._fire()));
    ['f','c'].forEach(id => this.querySelector('#'+id).addEventListener('change', ()=>this._fire()));
  }
  _fire() {
    this._config = {...this._config,
      entity: this.querySelector('#e').value,
      title: this.querySelector('#t').value,
      max_rows: parseInt(this.querySelector('#m').value)||10,
      show_route_filter: this.querySelector('#f').checked,
      compact: this.querySelector('#c').checked,
    };
    this.dispatchEvent(new CustomEvent('config-changed', {detail:{config:this._config}, bubbles:true, composed:true}));
  }
}

customElements.define('tranzy-transit-card', TranzyTransitCard);
customElements.define('tranzy-transit-card-editor', TranzyTransitCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({type:'tranzy-transit-card', name:'Tranzy Transit Card', description:'Real-time transit arrivals (Tranzy API)', preview:true});
console.info('%c TRANZY-TRANSIT %c v3.0 ','color:#fff;background:#ff9800;font-weight:bold;padding:2px 6px;border-radius:4px 0 0 4px','color:#ff9800;background:#fff3e0;font-weight:bold;padding:2px 6px;border-radius:0 4px 4px 0');
