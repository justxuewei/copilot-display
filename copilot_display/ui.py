"""Self-contained HTML UI for copilot-display."""

UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>copilot-display</title>
<style>
:root {
  --bg:           #0b0b0d;
  --surface:      #131316;
  --surface2:     #1a1a1f;
  --surface3:     #222228;
  --border:       #28282f;
  --border2:      #333340;
  --text:         #dddde8;
  --text-dim:     #7878a0;
  --text-faint:   #3a3a50;
  --accent:       #c0392b;
  --accent-hi:    #e8493a;
  --accent-lo:    rgba(192,57,43,0.15);
  --accent-dim:   #6b2018;
  --green:        #27ae60;
  --green-hi:     #2ecc71;
  --yellow:       #d68910;
  --blue:         #2471a3;
  --blue-hi:      #2e86c1;
  --mono: 'SF Mono','Cascadia Code','Fira Code','Consolas','Liberation Mono',monospace;
  --radius: 5px;
  --topbar-h: 44px;
  --sidebar-w: 172px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
}

/* ── Layout grid ─────────────────────────────────────────────────────────── */
.app {
  display: grid;
  grid-template-rows: var(--topbar-h) 1fr;
  grid-template-columns: var(--sidebar-w) 1fr;
  height: 100vh;
}

/* ── Topbar ──────────────────────────────────────────────────────────────── */
.topbar {
  grid-column: 1 / -1;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 14px;
  gap: 12px;
  position: relative;
  z-index: 10;
}

.logo {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text);
  user-select: none;
}
.logo em { color: var(--accent); font-style: normal; }

.topbar-sep {
  width: 1px;
  height: 16px;
  background: var(--border2);
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--text-dim);
}

.led {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--text-faint);
  transition: background 0.4s, box-shadow 0.4s;
  flex-shrink: 0;
}
.led.ok     { background: var(--green); box-shadow: 0 0 5px var(--green); }
.led.bad    { background: var(--accent); box-shadow: 0 0 5px var(--accent); }
.led.blink  { animation: blink 1s step-end infinite; }

@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }

.topbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.pill {
  padding: 3px 9px;
  border: 1px solid var(--border2);
  border-radius: 20px;
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  background: var(--surface2);
  font-family: var(--mono);
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
.sidebar {
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.nav-section-label {
  font-size: 9px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--text-faint);
  padding: 8px 14px 4px;
  user-select: none;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 14px;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--text-dim);
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: color 0.1s, background 0.1s, border-color 0.1s;
  user-select: none;
}
.nav-item:hover { color: var(--text); background: var(--surface2); }
.nav-item.active {
  color: var(--text);
  background: var(--surface2);
  border-left-color: var(--accent);
}

.nav-icon {
  width: 16px;
  text-align: center;
  font-size: 13px;
  flex-shrink: 0;
  opacity: 0.7;
}
.nav-item.active .nav-icon { opacity: 1; }

.sidebar-footer {
  margin-top: auto;
  padding: 12px 14px;
  font-size: 10px;
  color: var(--text-faint);
  letter-spacing: 0.06em;
  border-top: 1px solid var(--border);
}

/* ── Main area ───────────────────────────────────────────────────────────── */
.main { overflow: hidden; position: relative; }

.section {
  display: none;
  height: 100%;
  animation: fadein 0.15s ease;
}
.section.active { display: flex; }

@keyframes fadein { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }

/* ── Preview section ─────────────────────────────────────────────────────── */
#section-preview { flex-direction: row; }

.form-panel {
  width: 268px;
  min-width: 268px;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  scrollbar-width: thin;
  scrollbar-color: var(--border2) transparent;
}

.form-panel::-webkit-scrollbar { width: 4px; }
.form-panel::-webkit-scrollbar-track { background: transparent; }
.form-panel::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

.form-section {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-bottom: 1px solid var(--border);
}
.form-section:last-child { border-bottom: none; }

.form-heading {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.field { display: flex; flex-direction: column; gap: 4px; }

.field label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-dim);
}
.field label .req { color: var(--accent); margin-left: 2px; }

.field input,
.field textarea,
.field select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 7px 9px;
  font-family: var(--mono);
  font-size: 12px;
  color: var(--text);
  outline: none;
  width: 100%;
  transition: border-color 0.12s, background 0.12s;
  -webkit-appearance: none;
}
.field input:focus,
.field textarea:focus,
.field select:focus {
  border-color: var(--accent);
  background: var(--surface2);
}
.field input::placeholder,
.field textarea::placeholder { color: var(--text-faint); }
.field textarea { resize: vertical; min-height: 72px; }
.field select { cursor: pointer; background-image: none; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px;
  border: none;
  border-radius: var(--radius);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 0.12s;
  white-space: nowrap;
  user-select: none;
}
.btn:disabled { opacity: 0.3; cursor: not-allowed; pointer-events: none; }

.btn-primary  { background: var(--accent); color: #fff; }
.btn-primary:hover  { background: var(--accent-hi); }

.btn-ghost  { background: transparent; color: var(--text-dim); border: 1px solid var(--border2); }
.btn-ghost:hover  { color: var(--text); border-color: var(--text-dim); }

.btn-danger { background: transparent; color: var(--accent); border: 1px solid var(--accent-dim); }
.btn-danger:hover { background: var(--accent-lo); border-color: var(--accent); }

.btn-full { width: 100%; }

.btn-row { display: flex; gap: 8px; }

/* ── Display panel ───────────────────────────────────────────────────────── */
.display-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding: 28px;
  overflow: auto;
  background: var(--bg);
  background-image:
    linear-gradient(var(--surface) 1px, transparent 1px),
    linear-gradient(90deg, var(--surface) 1px, transparent 1px);
  background-size: 28px 28px;
}

/* Physical bezel */
.bezel-wrap { position: relative; }

.device-label {
  position: absolute;
  top: -22px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 9px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-faint);
  white-space: nowrap;
}

.eink-bezel {
  background: linear-gradient(145deg, #2c2c32, #1e1e24);
  border-radius: 14px;
  padding: 20px 22px 28px;
  box-shadow:
    0 0 0 1px #36363e,
    0 0 0 2px #111114,
    0 12px 40px rgba(0,0,0,0.7),
    0 4px 8px rgba(0,0,0,0.5),
    inset 0 1px 0 rgba(255,255,255,0.06);
  position: relative;
}

/* Notch / indicator dot */
.eink-bezel::before {
  content: '';
  position: absolute;
  top: 9px;
  left: 50%;
  transform: translateX(-50%);
  width: 28px; height: 4px;
  background: #111114;
  border-radius: 2px;
}
.eink-bezel::after {
  content: '';
  position: absolute;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  width: 6px; height: 6px;
  background: #1e1e24;
  border-radius: 50%;
  border: 1px solid #36363e;
  box-shadow: inset 0 0 0 1px #111114;
}

.eink-screen {
  width: 400px;
  height: 300px;
  background: #ddd8c4;
  border-radius: 3px;
  overflow: hidden;
  position: relative;
  box-shadow:
    inset 0 0 0 1px rgba(0,0,0,0.25),
    inset 0 2px 4px rgba(0,0,0,0.1);
}

.eink-screen img {
  display: block;
  width: 100%;
  height: 100%;
  image-rendering: pixelated;
  transition: opacity 0.2s;
}

.eink-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: #ddd8c4;
  color: #aaa89a;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.eink-placeholder svg { opacity: 0.25; }

.bezel-info {
  text-align: center;
  margin-top: 10px;
  font-size: 9px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #3a3a44;
}

/* Task status */
.task-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  border: 1px solid var(--border2);
  color: var(--text-faint);
  background: var(--surface2);
  transition: all 0.2s;
}
.status-chip .dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.status-chip.queued     { color: var(--yellow);  border-color: var(--yellow);  background: rgba(214,137,16,0.1); }
.status-chip.in_progress{ color: var(--blue-hi); border-color: var(--blue);    background: rgba(36,113,163,0.12); }
.status-chip.in_progress .dot { animation: pulse-dot 0.8s ease-in-out infinite; }
.status-chip.done       { color: var(--green-hi);border-color: var(--green);   background: rgba(39,174,96,0.1); }
.status-chip.failed     { color: var(--accent-hi);border-color: var(--accent); background: var(--accent-lo); }

@keyframes pulse-dot { 0%,100%{transform:scale(1);opacity:1} 50%{transform:scale(1.5);opacity:0.6} }

.task-id-label {
  font-size: 10px;
  color: var(--text-faint);
  letter-spacing: 0.04em;
}

.error-banner {
  max-width: 440px;
  padding: 8px 12px;
  background: var(--accent-lo);
  border: 1px solid var(--accent-dim);
  border-radius: var(--radius);
  font-size: 11px;
  color: #f0a090;
  line-height: 1.5;
}

/* ── Devices section ─────────────────────────────────────────────────────── */
#section-devices {
  flex-direction: column;
  padding: 20px 24px;
  gap: 14px;
  overflow-y: auto;
}

.section-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.section-hdr-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-dim);
}
.scan-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.spinner {
  width: 12px; height: 12px;
  border: 2px solid var(--border2);
  border-top-color: var(--text-dim);
  border-radius: 50%;
  animation: spin 0.55s linear infinite;
  display: none;
  flex-shrink: 0;
}
.spinner.active { display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

.scan-label { font-size: 10px; color: var(--text-dim); display: none; }
.scan-label.active { display: inline; }

.device-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.device-table th {
  padding: 7px 10px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-faint);
  border-bottom: 1px solid var(--border);
  text-align: left;
  white-space: nowrap;
}
.device-table td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.device-table tr:last-child td { border-bottom: none; }
.device-table tbody tr:hover td { background: var(--surface2); }
.device-table .addr-cell { color: var(--text-dim); font-size: 10px; }

.empty-row td {
  text-align: center;
  padding: 32px;
  color: var(--text-faint);
  font-size: 11px;
  letter-spacing: 0.08em;
}

/* Signal bars */
.sig-bars { display: flex; gap: 2px; align-items: flex-end; height: 14px; }
.sig-bars span {
  width: 4px;
  background: var(--border2);
  border-radius: 1px;
  flex-shrink: 0;
  transition: background 0.3s;
}
.sig-bars span.on { background: var(--green); }
.sig-bars span.on.med { background: var(--yellow); }
.sig-bars span.on.low { background: var(--accent); }

/* ── Health section ──────────────────────────────────────────────────────── */
#section-health {
  flex-direction: column;
  padding: 20px 24px;
  gap: 14px;
  overflow-y: auto;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}

.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: border-color 0.2s;
}
.stat-card:hover { border-color: var(--border2); }

.stat-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-faint);
}
.stat-value {
  font-size: 26px;
  font-weight: 400;
  font-family: var(--mono);
  color: var(--text);
  line-height: 1;
}
.stat-value.ok  { color: var(--green-hi); }
.stat-value.bad { color: var(--accent-hi); }
.stat-value.hi  { color: var(--yellow); }

.refresh-note {
  font-size: 10px;
  color: var(--text-faint);
  letter-spacing: 0.06em;
}

/* ── Settings section ────────────────────────────────────────────────────── */
#section-settings {
  flex-direction: column;
  padding: 20px 24px;
  gap: 14px;
  overflow-y: auto;
}

.config-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 460px;
}

.config-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-hint {
  font-size: 10px;
  color: var(--text-faint);
  line-height: 1.6;
  letter-spacing: 0.04em;
}

.config-note {
  font-size: 10px;
  letter-spacing: 0.06em;
  min-height: 16px;
}
.config-note.ok  { color: var(--green-hi); }
.config-note.err { color: var(--accent-hi); }

/* ── Auth overlay ────────────────────────────────────────────────────────── */
.auth-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.85);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.auth-box {
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: 8px;
  padding: 28px;
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.auth-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent-hi);
}
.auth-sub {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
}
.auth-sub code {
  background: var(--surface3);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text);
}
.auth-err {
  font-size: 11px;
  color: #f0a090;
  display: none;
}
</style>
</head>
<body>
<div class="app">

  <!-- ── Topbar ── -->
  <header class="topbar">
    <span class="logo">copilot<em>-display</em></span>
    <div class="topbar-sep"></div>
    <div class="health-indicator">
      <span class="led" id="health-led"></span>
      <span id="health-label">connecting…</span>
    </div>
    <div class="topbar-right">
      <span class="pill" id="version-pill">v—</span>
      <span class="pill" id="queue-pill">queue 0</span>
    </div>
  </header>

  <!-- ── Sidebar ── -->
  <nav class="sidebar">
    <span class="nav-section-label">Sections</span>
    <div class="nav-item active" data-target="preview">
      <span class="nav-icon">▤</span>Preview
    </div>
    <div class="nav-item" data-target="devices">
      <span class="nav-icon">◈</span>Devices
    </div>
    <div class="nav-item" data-target="health">
      <span class="nav-icon">◎</span>Health
    </div>
    <div class="nav-item" data-target="settings">
      <span class="nav-icon">⚙</span>Settings
    </div>
    <div class="sidebar-footer">BluTag 4.2″ · BLK/WHT/RED</div>
  </nav>

  <!-- ── Main ── -->
  <main class="main">

    <!-- ╔══ Preview ══╗ -->
    <section class="section active" id="section-preview">

      <div class="form-panel">

        <!-- Template selector -->
        <div class="form-section">
          <div class="form-heading">Template</div>
          <div class="field">
            <label>Type</label>
            <select id="tmpl-select"></select>
          </div>
        </div>

        <!-- Dynamic fields -->
        <div class="form-section" id="tmpl-fields-wrap">
          <div class="form-heading">Data</div>
          <div id="tmpl-fields"></div>
        </div>

        <!-- Device + actions -->
        <div class="form-section">
          <div class="form-heading">Output</div>
          <div class="field">
            <label>Device</label>
            <select id="device-select">
              <option value="">Default</option>
            </select>
          </div>
          <div class="btn-row">
            <button class="btn btn-primary" id="btn-preview">Preview</button>
            <button class="btn btn-ghost" id="btn-push" disabled>Push ▶</button>
          </div>
        </div>

        <!-- Clear -->
        <div class="form-section">
          <div class="form-heading">Maintenance</div>
          <button class="btn btn-danger btn-full" id="btn-clear">Clear display</button>
        </div>

      </div>

      <!-- Display frame -->
      <div class="display-panel">
        <div class="bezel-wrap">
          <span class="device-label">LANCOS BluTag 4.2″ e-ink display</span>
          <div class="eink-bezel">
            <div class="eink-screen" id="eink-screen">
              <div class="eink-placeholder" id="eink-placeholder">
                <svg width="48" height="36" viewBox="0 0 48 36" fill="none">
                  <rect x="1" y="1" width="46" height="34" rx="2" stroke="#888" stroke-width="1.5"/>
                  <rect x="8" y="8" width="32" height="3" rx="1" fill="#888"/>
                  <rect x="8" y="15" width="24" height="2" rx="1" fill="#888"/>
                  <rect x="8" y="21" width="28" height="2" rx="1" fill="#888"/>
                </svg>
                <span>no preview</span>
              </div>
            </div>
          </div>
          <div class="bezel-info">400 × 300 px · tri-color</div>
        </div>

        <div class="task-row">
          <span class="status-chip" id="task-chip">
            <span class="dot"></span>
            <span id="task-chip-text">idle</span>
          </span>
          <span class="task-id-label" id="task-id-label"></span>
        </div>

        <div class="error-banner" id="preview-error" style="display:none"></div>
      </div>
    </section>

    <!-- ╔══ Devices ══╗ -->
    <section class="section" id="section-devices">
      <div class="section-hdr">
        <span class="section-hdr-title">Bluetooth devices</span>
        <div class="scan-row">
          <span class="spinner" id="scan-spinner"></span>
          <span class="scan-label" id="scan-label">Scanning…</span>
          <button class="btn btn-ghost" id="btn-scan">Scan</button>
        </div>
      </div>
      <table class="device-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Address</th>
            <th>RSSI</th>
            <th>Signal</th>
          </tr>
        </thead>
        <tbody id="devices-tbody">
          <tr class="empty-row"><td colspan="4">No devices cached — run a scan.</td></tr>
        </tbody>
      </table>
    </section>

    <!-- ╔══ Health ══╗ -->
    <section class="section" id="section-health">
      <div class="section-hdr">
        <span class="section-hdr-title">System health</span>
        <span class="refresh-note" id="refresh-note">auto-refresh every 5 s</span>
      </div>
      <div class="stat-grid">
        <div class="stat-card">
          <span class="stat-label">Status</span>
          <span class="stat-value" id="stat-status">—</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">Version</span>
          <span class="stat-value" id="stat-version" style="font-size:20px">—</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">Devices</span>
          <span class="stat-value" id="stat-devices">—</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">Queue depth</span>
          <span class="stat-value" id="stat-queue">—</span>
        </div>
      </div>
    </section>

    <!-- ╔══ Settings ══╗ -->
    <section class="section" id="section-settings">
      <div class="section-hdr">
        <span class="section-hdr-title">Settings</span>
        <button class="btn btn-primary" id="btn-save-config">Save</button>
      </div>
      <div class="config-grid">
        <div class="config-card">
          <div class="form-heading">Scheduling</div>
          <div class="field">
            <label>Scan interval (s) — 0 to disable</label>
            <input type="number" id="cfg-scan_interval" min="0" step="1" placeholder="60">
          </div>
          <div class="field">
            <label>Refresh interval (s) — 0 to disable</label>
            <input type="number" id="cfg-refresh_interval" min="0" step="1" placeholder="300">
          </div>
        </div>
        <div class="config-card">
          <div class="form-heading">Work hours</div>
          <div class="two-col">
            <div class="field">
              <label>Start</label>
              <input type="time" id="cfg-work_start">
            </div>
            <div class="field">
              <label>End</label>
              <input type="time" id="cfg-work_end">
            </div>
          </div>
          <div class="field-hint">Outside work hours, background tasks are paused. Leave both empty to always run.</div>
        </div>
      </div>
      <span class="config-note" id="config-note"></span>
    </section>

  </main>
</div>

<!-- ── Auth overlay ── -->
<div class="auth-overlay" id="auth-overlay" style="display:none">
  <div class="auth-box">
    <div class="auth-title">Authentication required</div>
    <p class="auth-sub">The server requires an API token. Enter it below — it will be sent as <code>X-API-Token</code> on every request.</p>
    <div class="field">
      <label>Token</label>
      <input type="password" id="auth-input" autocomplete="off" placeholder="enter token…">
    </div>
    <div class="auth-err" id="auth-err">Token cannot be empty.</div>
    <button class="btn btn-primary btn-full" id="auth-submit">Authenticate</button>
  </div>
</div>

<script>
// ═══════════════════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════════════════
let apiToken = '';
let authResolve = null;
let lastPreviewPayload = null;  // {template, data} of last successful preview
let taskPollTimer = null;
let healthTimer = null;
let _savedConfig = {};  // local mirror of server config.json

// ═══════════════════════════════════════════════════════════════════════════
// Auth
// ═══════════════════════════════════════════════════════════════════════════
function requireAuth() {
  return new Promise(resolve => {
    authResolve = resolve;
    document.getElementById('auth-overlay').style.display = 'flex';
    document.getElementById('auth-input').focus();
  });
}

document.getElementById('auth-submit').addEventListener('click', submitAuth);
document.getElementById('auth-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') submitAuth();
});

function submitAuth() {
  const val = document.getElementById('auth-input').value.trim();
  const errEl = document.getElementById('auth-err');
  if (!val) { errEl.style.display = 'block'; return; }
  errEl.style.display = 'none';
  apiToken = val;
  document.getElementById('auth-overlay').style.display = 'none';
  if (authResolve) { authResolve(); authResolve = null; }
}

// ═══════════════════════════════════════════════════════════════════════════
// Fetch wrapper (auto 401 handling + JSON body)
// ═══════════════════════════════════════════════════════════════════════════
async function api(path, opts = {}) {
  const headers = { ...opts.headers };
  if (!(opts.body instanceof Blob)) headers['Content-Type'] = 'application/json';
  if (apiToken) headers['X-API-Token'] = apiToken;

  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    await requireAuth();
    return api(path, opts);
  }
  return res;
}

// ═══════════════════════════════════════════════════════════════════════════
// Navigation
// ═══════════════════════════════════════════════════════════════════════════
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    item.classList.add('active');
    document.getElementById('section-' + item.dataset.target).classList.add('active');

    const t = item.dataset.target;
    if (t === 'devices') loadDevices();
    if (t === 'health') { clearTimeout(healthTimer); refreshHealth(); }
    if (t === 'settings') loadConfig();
  });
});

// ═══════════════════════════════════════════════════════════════════════════
// Template definitions & form builder
// ═══════════════════════════════════════════════════════════════════════════
// Per-template JSON examples shown in the textarea fallback
const TMPL_EXAMPLES = {
};

const TMPL_FIELDS = {
  text: [
    { key: 'title',       label: 'Title',       type: 'text',     placeholder: 'Hello' },
    { key: 'body',        label: 'Body',        type: 'textarea', placeholder: 'Body text…', required: true },
    { key: 'title_color', label: 'Title color', type: 'select',   options: ['red','black'],   default: 'red' },
    { key: 'body_color',  label: 'Body color',  type: 'select',   options: ['black','red'],   default: 'black' },
  ],
  stock: [
    { key: 'sym1', label: 'Ticker 1', type: 'text', placeholder: '^IXIC',  default: '^IXIC' },
    { key: 'sym2', label: 'Ticker 2', type: 'text', placeholder: '^GSPC',  default: '^GSPC' },
    { key: 'sym3', label: 'Ticker 3', type: 'text', placeholder: 'GC=F',   default: 'GC=F' },
    { key: 'sym4', label: 'Ticker 4', type: 'text', placeholder: 'BZ=F',   default: 'BZ=F' },
  ],
};

function buildForm(name) {
  const container = document.getElementById('tmpl-fields');
  container.innerHTML = '';

  document.getElementById('btn-preview').textContent = (name === 'stock') ? 'Fetch & Preview' : 'Preview';

  const fields = TMPL_FIELDS[name];
  if (!fields) {
    const wrap = makeField('Data (JSON)', 'raw-json', 'textarea', '');
    const ta = wrap.querySelector('textarea');
    ta.value = TMPL_EXAMPLES[name] || '{}';
    ta.style.minHeight = '220px';
    container.appendChild(wrap);
  } else if (name === 'stock') {
    const grid = document.createElement('div');
    grid.className = 'two-col';
    fields.forEach(f => {
      const wrap = makeField(f.label, 'f_' + f.key, f.type, f.placeholder || '', f.required, f.step);
      const input = wrap.querySelector('input');
      if (f.default) input.value = f.default;
      grid.appendChild(wrap);
    });
    container.appendChild(grid);
  } else {
    const selects = fields.filter(f => f.type === 'select');
    const others  = fields.filter(f => f.type !== 'select');
    others.forEach(f => container.appendChild(makeField(f.label, 'f_' + f.key, f.type, f.placeholder || '', f.required, f.step)));
    if (selects.length) {
      const row = document.createElement('div');
      row.className = 'two-col';
      selects.forEach(f => {
        const wrap = document.createElement('div');
        wrap.className = 'field';
        const lbl = document.createElement('label');
        lbl.textContent = f.label;
        const sel = document.createElement('select');
        sel.id = 'f_' + f.key;
        f.options.forEach(o => {
          const opt = document.createElement('option');
          opt.value = opt.textContent = o;
          if (o === f.default) opt.selected = true;
          sel.appendChild(opt);
        });
        wrap.appendChild(lbl);
        wrap.appendChild(sel);
        row.appendChild(wrap);
      });
      container.appendChild(row);
    }
  }
  restoreTemplateFields(name);
}

function makeField(label, id, type, placeholder, required, step) {
  const wrap = document.createElement('div');
  wrap.className = 'field';
  const lbl = document.createElement('label');
  lbl.innerHTML = label + (required ? '<span class="req">*</span>' : '');
  let el;
  if (type === 'textarea') {
    el = document.createElement('textarea');
    el.placeholder = placeholder;
  } else {
    el = document.createElement('input');
    el.type = type;
    el.placeholder = placeholder;
    if (step) el.step = step;
  }
  el.id = id;
  wrap.appendChild(lbl);
  wrap.appendChild(el);
  return wrap;
}

function collectData(name) {
  const fields = TMPL_FIELDS[name];
  if (!fields) {
    const raw = document.getElementById('raw-json')?.value || '{}';
    return JSON.parse(raw);
  }
  const data = {};
  fields.forEach(f => {
    const el = document.getElementById('f_' + f.key);
    if (!el) return;
    const v = el.value.trim();
    if (!v) return;
    data[f.key] = f.type === 'number' ? parseFloat(v) : v;
  });
  return data;
}

// ═══════════════════════════════════════════════════════════════════════════
// Load templates dropdown
// ═══════════════════════════════════════════════════════════════════════════
async function loadTemplates() {
  try {
    const res = await api('/api/templates');
    if (!res.ok) return;
    const { templates } = await res.json();
    const sel = document.getElementById('tmpl-select');
    sel.innerHTML = '';
    templates.forEach(name => {
      const opt = document.createElement('option');
      opt.value = opt.textContent = name;
      sel.appendChild(opt);
    });
    if (_savedConfig.template && templates.includes(_savedConfig.template)) sel.value = _savedConfig.template;
    buildForm(sel.value);
  } catch {}
}

document.getElementById('tmpl-select').addEventListener('change', e => {
  saveTemplateState();
  buildForm(e.target.value);
  lastPreviewPayload = null;
  document.getElementById('btn-push').disabled = true;
  setChip('', 'idle');
});

// ═══════════════════════════════════════════════════════════════════════════
// Device dropdown (for preview panel)
// ═══════════════════════════════════════════════════════════════════════════
async function loadDeviceDropdown() {
  try {
    const res = await api('/api/devices');
    if (!res.ok) return;
    const devices = await res.json();
    const sel = document.getElementById('device-select');
    while (sel.options.length > 1) sel.remove(1);
    devices.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.address;
      opt.textContent = (d.name || 'Unknown') + ' · ' + d.address;
      sel.appendChild(opt);
    });
  } catch {}
}

// ═══════════════════════════════════════════════════════════════════════════
// Preview
// ═══════════════════════════════════════════════════════════════════════════
document.getElementById('btn-preview').addEventListener('click', async () => {
  const name = document.getElementById('tmpl-select').value;
  const isStock = (name === 'stock');

  hideError();
  const btn = document.getElementById('btn-preview');
  btn.disabled = true;
  btn.textContent = isStock ? 'Fetching…' : '…';

  try {
    let previewRes;

    if (isStock) {
      // Collect ticker symbols from inputs
      const symbols = ['sym1','sym2','sym3','sym4']
        .map(k => (document.getElementById('f_' + k)?.value || '').trim())
        .filter(Boolean);
      if (!symbols.length) throw new Error('Enter at least one ticker symbol');

      // Fetch live data via /api/preview/stocks
      const fetchRes = await api('/api/preview/stocks', {
        method: 'POST',
        body: JSON.stringify({ symbols }),
      });
      if (!fetchRes.ok) {
        const err = await fetchRes.json().catch(() => ({ detail: fetchRes.statusText }));
        throw new Error(err.detail ?? fetchRes.statusText);
      }
      const blob = await fetchRes.blob();
      const url  = URL.createObjectURL(blob);

      const screen = document.getElementById('eink-screen');
      screen.innerHTML = '';
      const img = document.createElement('img');
      img.src = url;
      screen.appendChild(img);

      // Store for push — use the stocks endpoint
      lastPreviewPayload = { _stockPush: true, symbols };
      document.getElementById('btn-push').disabled = false;
      setChip('', 'ready to push');
    } else {
      let data;
      try { data = collectData(name); }
      catch (e) { throw new Error('Invalid JSON: ' + e.message); }

      previewRes = await api('/api/preview/template', {
        method: 'POST',
        body: JSON.stringify({ template: name, data }),
      });
      if (!previewRes.ok) {
        const err = await previewRes.json().catch(() => ({ detail: previewRes.statusText }));
        throw new Error(err.detail ?? previewRes.statusText);
      }
      const blob = await previewRes.blob();
      const url  = URL.createObjectURL(blob);

      const screen = document.getElementById('eink-screen');
      screen.innerHTML = '';
      const img = document.createElement('img');
      img.src = url;
      screen.appendChild(img);

      lastPreviewPayload = { template: name, data };
      document.getElementById('btn-push').disabled = false;
      setChip('', 'ready to push');
    }
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = isStock ? 'Fetch & Preview' : 'Preview';
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// Push
// ═══════════════════════════════════════════════════════════════════════════
document.getElementById('btn-push').addEventListener('click', async () => {
  if (!lastPreviewPayload) return;
  const device = document.getElementById('device-select').value || undefined;
  const btn = document.getElementById('btn-push');
  btn.disabled = true;
  setChip('queued', 'queuing…');
  hideError();

  try {
    let res;
    if (lastPreviewPayload._stockPush) {
      // Use the stocks push endpoint
      res = await api('/api/push/stocks', {
        method: 'POST',
        body: JSON.stringify({ symbols: lastPreviewPayload.symbols, ...(device ? { device } : {}) }),
      });
    } else {
      const payload = { ...lastPreviewPayload, ...(device ? { device } : {}) };
      res = await api('/api/push/template', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail ?? res.statusText);
    }
    const json = await res.json();
    setChip('queued', 'queued');
    document.getElementById('task-id-label').textContent = json.task_id.slice(0, 8) + '…';
    pollTask(json.task_id);
  } catch (e) {
    setChip('failed', 'push failed');
    showError(e.message);
    btn.disabled = false;
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// Clear
// ═══════════════════════════════════════════════════════════════════════════
document.getElementById('btn-clear').addEventListener('click', async () => {
  const btn = document.getElementById('btn-clear');
  btn.disabled = true;
  btn.textContent = 'Clearing…';
  setChip('in_progress', 'clearing');
  hideError();

  try {
    const device = document.getElementById('device-select').value || undefined;
    const res = await api('/api/clear' + (device ? '?device=' + encodeURIComponent(device) : ''), { method: 'POST' });
    if (!res.ok) throw new Error('Clear failed: ' + res.statusText);
    const json = await res.json();
    setChip('queued', 'queued');
    document.getElementById('task-id-label').textContent = json.task_id.slice(0, 8) + '…';
    pollTask(json.task_id, () => {
      // Reset display frame
      document.getElementById('eink-screen').innerHTML =
        '<div class="eink-placeholder"><svg width="48" height="36" viewBox="0 0 48 36" fill="none"><rect x="1" y="1" width="46" height="34" rx="2" stroke="#aaa89a" stroke-width="1.5"/></svg><span>cleared</span></div>';
      lastPreviewPayload = null;
      document.getElementById('btn-push').disabled = true;
    });
  } catch (e) {
    setChip('failed', 'failed');
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Clear display';
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// Task polling
// ═══════════════════════════════════════════════════════════════════════════
function pollTask(id, onDone) {
  clearTimeout(taskPollTimer);
  taskPollTimer = setTimeout(async () => {
    try {
      const res = await api('/api/tasks/' + id);
      if (!res.ok) { setChip('failed', 'error'); return; }
      const task = await res.json();
      setChip(task.status, task.status.replace('_', ' '));
      if (task.status === 'queued' || task.status === 'in_progress') {
        pollTask(id, onDone);
      } else {
        document.getElementById('btn-push').disabled = false;
        if (task.status === 'done' && onDone) onDone();
      }
    } catch {
      setChip('failed', 'error');
      document.getElementById('btn-push').disabled = false;
    }
  }, 2000);
}

// ═══════════════════════════════════════════════════════════════════════════
// Status chip helpers
// ═══════════════════════════════════════════════════════════════════════════
function setChip(cls, text) {
  const chip = document.getElementById('task-chip');
  chip.className = 'status-chip' + (cls ? ' ' + cls : '');
  document.getElementById('task-chip-text').textContent = text;
  if (!cls) document.getElementById('task-id-label').textContent = '';
}

function showError(msg) {
  const el = document.getElementById('preview-error');
  el.textContent = msg;
  el.style.display = 'block';
}
function hideError() {
  document.getElementById('preview-error').style.display = 'none';
}

// ═══════════════════════════════════════════════════════════════════════════
// Devices section
// ═══════════════════════════════════════════════════════════════════════════
async function loadDevices() {
  try {
    const res = await api('/api/devices');
    if (!res.ok) return;
    renderDevices(await res.json());
  } catch {}
}

function renderDevices(devices) {
  const tbody = document.getElementById('devices-tbody');
  if (!devices.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="4">No devices found. Run a scan to discover nearby BLE devices.</td></tr>';
    return;
  }
  tbody.innerHTML = devices.map(d => {
    const rssi = d.rssi ?? null;
    return `<tr>
      <td>${esc(d.name || '—')}</td>
      <td class="addr-cell">${esc(d.address)}</td>
      <td style="color:var(--text-dim)">${rssi != null ? rssi + ' dBm' : '—'}</td>
      <td>${sigBars(rssi)}</td>
    </tr>`;
  }).join('');
}

function sigBars(rssi) {
  const levels = rssi == null ? 0 : rssi >= -60 ? 4 : rssi >= -70 ? 3 : rssi >= -80 ? 2 : rssi >= -90 ? 1 : 0;
  const qual   = rssi == null ? '' : rssi >= -70 ? '' : rssi >= -80 ? 'med' : 'low';
  const heights = [5, 8, 11, 14];
  return '<div class="sig-bars">' +
    heights.map((h, i) => `<span style="height:${h}px" class="${i < levels ? 'on ' + qual : ''}"></span>`).join('') +
  '</div>';
}

document.getElementById('btn-scan').addEventListener('click', async () => {
  const btn     = document.getElementById('btn-scan');
  const spinner = document.getElementById('scan-spinner');
  const label   = document.getElementById('scan-label');
  btn.disabled = true;
  spinner.classList.add('active');
  label.classList.add('active');

  try {
    const res = await api('/api/devices/scan', { method: 'POST' });
    if (!res.ok) throw new Error();
    const json = await res.json();
    renderDevices(json.devices);
    loadDeviceDropdown();
  } catch {} finally {
    btn.disabled = false;
    spinner.classList.remove('active');
    label.classList.remove('active');
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// Health section
// ═══════════════════════════════════════════════════════════════════════════
async function refreshHealth() {
  try {
    const res = await api('/api/health');
    if (!res.ok) throw new Error();
    const h = await res.json();

    // Topbar
    const led = document.getElementById('health-led');
    led.className = 'led ' + (h.status === 'ok' ? 'ok' : 'bad');
    document.getElementById('health-label').textContent = h.status === 'ok' ? 'online' : 'error';
    document.getElementById('version-pill').textContent = 'v' + (h.version ?? '?');
    document.getElementById('queue-pill').textContent   = 'queue ' + (h.queue_depth ?? 0);

    // Stat cards
    const sv = document.getElementById('stat-status');
    sv.textContent  = h.status;
    sv.className    = 'stat-value ' + (h.status === 'ok' ? 'ok' : 'bad');
    document.getElementById('stat-version').textContent = h.version ?? '—';
    document.getElementById('stat-devices').textContent = h.devices ?? 0;
    const sq = document.getElementById('stat-queue');
    sq.textContent = h.queue_depth ?? 0;
    sq.className   = 'stat-value' + ((h.queue_depth ?? 0) > 0 ? ' hi' : '');
    document.getElementById('refresh-note').textContent = 'last refresh ' + new Date().toLocaleTimeString();
  } catch {
    document.getElementById('health-led').className = 'led bad';
    document.getElementById('health-label').textContent = 'unreachable';
  }
  healthTimer = setTimeout(refreshHealth, 5000);
}

// ═══════════════════════════════════════════════════════════════════════════
// Template state persistence (server config)
// ═══════════════════════════════════════════════════════════════════════════

// Reads from _savedConfig — called synchronously from buildForm after DOM is built.
function restoreTemplateFields(name) {
  if (_savedConfig.template !== name || !_savedConfig.template_data) return;
  const data = _savedConfig.template_data;
  const fields = TMPL_FIELDS[name];
  if (fields) {
    fields.forEach(f => {
      const el = document.getElementById('f_' + f.key);
      if (el && data[f.key] !== undefined) el.value = data[f.key];
    });
  } else {
    const ta = document.getElementById('raw-json');
    if (ta && data._raw !== undefined) ta.value = data._raw;
  }
}

// Collect current field values and PATCH to server config.
async function saveTemplateState() {
  const name = document.getElementById('tmpl-select').value;
  if (!name) return;
  const fields = TMPL_FIELDS[name];
  const template_data = {};
  if (fields) {
    fields.forEach(f => {
      const el = document.getElementById('f_' + f.key);
      if (el) template_data[f.key] = el.value;
    });
  } else {
    const ta = document.getElementById('raw-json');
    if (ta) template_data._raw = ta.value;
  }
  _savedConfig.template = name;
  _savedConfig.template_data = template_data;
  await api('/api/config', {
    method: 'PATCH',
    body: JSON.stringify({ template: name, template_data }),
  }).catch(() => {});
}

// Save on any field change within the form panel (debounced)
let _tmplSaveTimer = null;
document.querySelector('.form-panel').addEventListener('input', () => {
  clearTimeout(_tmplSaveTimer);
  _tmplSaveTimer = setTimeout(saveTemplateState, 400);
});

// ═══════════════════════════════════════════════════════════════════════════
// Settings section
// ═══════════════════════════════════════════════════════════════════════════
async function loadConfig() {
  try {
    const res = await api('/api/config');
    if (!res.ok) return;
    _savedConfig = await res.json();
    document.getElementById('cfg-scan_interval').value    = _savedConfig.scan_interval    ?? 60;
    document.getElementById('cfg-refresh_interval').value = _savedConfig.refresh_interval ?? 300;
    document.getElementById('cfg-work_start').value       = _savedConfig.work_start       ?? '';
    document.getElementById('cfg-work_end').value         = _savedConfig.work_end         ?? '';
  } catch {}
}

document.getElementById('btn-save-config').addEventListener('click', async () => {
  const btn  = document.getElementById('btn-save-config');
  const note = document.getElementById('config-note');
  btn.disabled = true;
  note.textContent = '';
  note.className = 'config-note';
  try {
    const updates = {
      scan_interval:    parseInt(document.getElementById('cfg-scan_interval').value,    10) || 0,
      refresh_interval: parseInt(document.getElementById('cfg-refresh_interval').value, 10) || 0,
      work_start: document.getElementById('cfg-work_start').value.trim(),
      work_end:   document.getElementById('cfg-work_end').value.trim(),
    };
    const res = await api('/api/config', { method: 'PATCH', body: JSON.stringify(updates) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
    _savedConfig = await res.json();
    note.textContent = 'Saved. Restart server to apply scheduling changes.';
    note.className = 'config-note ok';
  } catch (e) {
    note.textContent = e.message;
    note.className = 'config-note err';
  } finally {
    btn.disabled = false;
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// Utils
// ═══════════════════════════════════════════════════════════════════════════
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ═══════════════════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════════════════
(async () => {
  // Load config first so _savedConfig is ready before buildForm restores template fields
  try {
    const res = await api('/api/config');
    if (res.ok) _savedConfig = await res.json();
  } catch {}
  await loadTemplates();
  await loadDeviceDropdown();
  refreshHealth();
})();
</script>
</body>
</html>"""
