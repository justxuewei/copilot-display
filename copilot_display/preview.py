"""HTML for the template preview page."""

PREVIEW_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>copilot-display preview</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f5f5f5;
    color: #1a1a1a;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 32px 16px;
    gap: 24px;
  }

  h1 {
    font-size: 1.25rem;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: #111;
  }

  .card {
    background: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 24px;
    width: 100%;
    max-width: 520px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  label {
    font-size: 0.8rem;
    font-weight: 500;
    color: #555;
    display: block;
    margin-bottom: 5px;
  }

  select, textarea {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    font-size: 0.9rem;
    background: #fafafa;
    color: #1a1a1a;
    outline: none;
    transition: border-color 0.15s;
  }
  select:focus, textarea:focus { border-color: #888; background: #fff; }

  textarea {
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    font-size: 0.82rem;
    resize: vertical;
    min-height: 180px;
  }

  .actions { display: flex; gap: 10px; }

  button {
    flex: 1;
    padding: 9px 0;
    border: none;
    border-radius: 6px;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  button:disabled { opacity: 0.45; cursor: not-allowed; }

  #btn-preview { background: #1a1a1a; color: #fff; }
  #btn-push    { background: #c0392b; color: #fff; }
  #btn-preview:hover:not(:disabled) { background: #333; }
  #btn-push:hover:not(:disabled)    { background: #a93226; }

  .status {
    font-size: 0.8rem;
    color: #666;
    min-height: 1.2em;
    text-align: center;
  }
  .status.error { color: #c0392b; }
  .status.ok    { color: #27ae60; }

  .preview-box {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }

  .display-frame {
    border: 2px solid #ccc;
    border-radius: 4px;
    background: #fff;
    /* 400x300 @ 2x scale */
    width: 400px;
    height: 300px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #bbb;
    font-size: 0.8rem;
    overflow: hidden;
    position: relative;
  }

  .display-frame img {
    width: 400px;
    height: 300px;
    display: block;
    image-rendering: pixelated;
  }

  .frame-label {
    font-size: 0.72rem;
    color: #999;
  }
</style>
</head>
<body>

<h1>copilot-display &mdash; template preview</h1>

<div class="card">
  <div>
    <label for="tmpl-select">Template</label>
    <select id="tmpl-select"></select>
  </div>

  <div>
    <label for="data-input">Data <span style="font-weight:400;color:#999">(JSON)</span></label>
    <textarea id="data-input" spellcheck="false"></textarea>
  </div>

  <div class="actions">
    <button id="btn-preview">Preview</button>
    <button id="btn-push" disabled>Push to display</button>
  </div>

  <div class="status" id="status"></div>
</div>

<div class="preview-box">
  <div class="display-frame" id="frame">
    <span>preview will appear here</span>
  </div>
  <span class="frame-label">400 &times; 300 &mdash; actual display size</span>
</div>

<script>
const EXAMPLES = {
  stock: {
    symbol: "AAPL",
    price: 189.30,
    change: 1.20,
    change_pct: 0.64,
    currency: "USD",
    label: "NASDAQ"
  },
  text: {
    title: "Hello",
    body: "This is a preview of the text template.",
    title_color: "red",
    body_color: "black"
  }
};

const select   = document.getElementById("tmpl-select");
const textarea = document.getElementById("data-input");
const btnPrev  = document.getElementById("btn-preview");
const btnPush  = document.getElementById("btn-push");
const status   = document.getElementById("status");
const frame    = document.getElementById("frame");

let lastPreviewData = null;   // {template, data} of the last successful preview

// ── Load templates ────────────────────────────────────────────────────────────
async function loadTemplates() {
  try {
    const res = await fetch("/api/templates");
    const json = await res.json();
    json.templates.forEach(name => {
      const opt = document.createElement("option");
      opt.value = opt.textContent = name;
      select.appendChild(opt);
    });
    populateExample();
  } catch (e) {
    setStatus("Failed to load templates: " + e.message, "error");
  }
}

function populateExample() {
  const name = select.value;
  const ex = EXAMPLES[name] || {};
  textarea.value = JSON.stringify(ex, null, 2);
  lastPreviewData = null;
  btnPush.disabled = true;
}

select.addEventListener("change", populateExample);

// ── Preview ───────────────────────────────────────────────────────────────────
btnPrev.addEventListener("click", async () => {
  let data;
  try {
    data = JSON.parse(textarea.value);
  } catch {
    setStatus("Invalid JSON in data field.", "error");
    return;
  }

  setStatus("Rendering…");
  btnPrev.disabled = true;

  try {
    const res = await fetch("/api/preview/template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template: select.value, data })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail ?? res.statusText);
    }

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);

    frame.innerHTML = "";
    const img = document.createElement("img");
    img.src = url;
    img.alt = "display preview";
    frame.appendChild(img);

    lastPreviewData = { template: select.value, data };
    btnPush.disabled = false;
    setStatus("Rendered successfully.", "ok");
  } catch (e) {
    setStatus("Preview error: " + e.message, "error");
  } finally {
    btnPrev.disabled = false;
  }
});

// ── Push ─────────────────────────────────────────────────────────────────────
btnPush.addEventListener("click", async () => {
  if (!lastPreviewData) return;
  setStatus("Pushing to display…");
  btnPush.disabled = true;

  try {
    const res = await fetch("/api/push/template", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lastPreviewData)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail ?? res.statusText);
    }

    const json = await res.json();
    setStatus(`Queued — task ${json.task_id.slice(0, 8)}…`, "ok");
  } catch (e) {
    setStatus("Push error: " + e.message, "error");
    btnPush.disabled = false;
  }
});

function setStatus(msg, cls = "") {
  status.textContent = msg;
  status.className = "status " + cls;
}

loadTemplates();
</script>
</body>
</html>
"""
