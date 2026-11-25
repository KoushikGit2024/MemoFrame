HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MemoFrame Test Harness</title>
<style>
  :root { --bg: #121417; --card: #1c2026; --border: #2e3642; --text: #e6edf3; --dim: #8b949e; --accent: #2f81f7; --success: #238636; --danger: #da3633; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); }
  h1, h2, h3 { margin-top: 0; }
  .grid { display: grid; grid-template-columns: 340px 1fr; gap: 20px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 20px; }
  button { background: var(--accent); color: #fff; border: 0; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-weight: 600; }
  button:hover { opacity: 0.9; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  button.sec { background: #30363d; }
  button.danger { background: var(--danger); }
  input, select { width: 100%; padding: 8px 10px; border-radius: 6px; background: #0d1117; border: 1px solid var(--border); color: var(--text); margin-bottom: 10px; }
  label { font-size: 12px; color: var(--dim); display: block; margin-bottom: 4px; }
  .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
  .item { background: #15191e; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; position: relative; }
  .thumb-wrap { position: relative; width: 100%; aspect-ratio: 4/3; background: #0a0c0e; display: flex; align-items: center; justify-content: center; overflow: hidden; }
  .thumb-wrap img { width: 100%; height: 100%; object-fit: contain; }
  .box { position: absolute; border: 2px solid #58a6ff; background: rgba(88, 166, 255, 0.2); pointer-events: none; border-radius: 2px; }
  .meta { padding: 10px; font-size: 12px; }
  .meta b { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .badge { display: inline-block; padding: 2px 6px; border-radius: 12px; font-size: 10px; font-weight: 600; background: #21262d; margin-top: 4px; border: 1px solid var(--border); }
  .person-badge { background: #1f364d; border-color: #388bfd; color: #79c0ff; }
  pre { background: #0d1117; border: 1px solid var(--border); border-radius: 6px; padding: 12px; overflow: auto; max-height: 250px; font-size: 12px; }
  #status-bar { padding: 8px 12px; background: #161b22; border-radius: 6px; border: 1px solid var(--border); margin-bottom: 16px; font-size: 13px; }

  /* People Horizontal Bar */
  .people-bar { display: flex; gap: 12px; overflow-x: auto; padding: 8px 0; margin-bottom: 12px; }
  .person-pill { flex: 0 0 auto; background: #161b22; border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; display: flex; align-items: center; gap: 8px; cursor: pointer; transition: all 0.2s ease; }
  .person-pill:hover, .person-pill.active { border-color: var(--accent); background: #1f2733; }
  .person-avatar { width: 34px; height: 34px; border-radius: 50%; object-fit: cover; background: #21262d; }
  .person-name { font-size: 12px; font-weight: 600; }
  .person-count { font-size: 11px; color: var(--dim); }

  /* Progress Box */
  .progress-box { background: #0d1117; border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin-top: 12px; display: none; }
  .progress-track { width: 100%; height: 8px; background: #21262d; border-radius: 4px; overflow: hidden; margin: 8px 0; }
  .progress-fill { width: 0%; height: 100%; background: var(--accent); transition: width 0.2s ease; }
  .step-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; font-size: 11px; }
  .step { display: flex; align-items: center; gap: 6px; color: var(--dim); }
  .step.active { color: #58a6ff; font-weight: 600; }
  .step.done { color: #3fb950; }
  .step-icon { width: 12px; text-align: center; }
</style>
</head>
<body>
<h1>MemoFrame Local Test Dashboard</h1>
<div id="status-bar">Status: Ready. Workspace: <code>__WORKSPACE__</code></div>

<div class="grid">
  <!-- Left Control Panel -->
  <div>
    <div class="card">
      <h3>Rescan Folder</h3>
      <label>Folder Path to Scan</label>
      <input type="text" id="scan-path" placeholder="e.g. D:\Photos or leave empty for known">
      <div style="display:flex;gap:8px;">
        <button id="btn-rescan" onclick="startRescan()" style="flex:1">Start Rescan</button>
        <button id="btn-cancel" onclick="cancelRescan()" class="danger" style="display:none;">Cancel</button>
      </div>

      <!-- Live Progress & Process Steps -->
      <div id="progress-box" class="progress-box">
        <div style="display:flex;justify-content:space-between;font-size:12px;">
          <b id="prog-stage">Stage: Initializing...</b>
          <span id="prog-count">0 / 0</span>
        </div>
        <div class="progress-track">
          <div id="prog-bar" class="progress-fill"></div>
        </div>
        <div id="prog-current" style="font-size:11px;color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Processing...</div>

        <div class="step-list">
          <div class="step" id="step-scan"><span class="step-icon">○</span> 1. Directory Scan & Metadata Check</div>
          <div class="step" id="step-process"><span class="step-icon">○</span> 2. Face Detection & Feature Extraction</div>
          <div class="step" id="step-duplicates"><span class="step-icon">○</span> 3. Duplicate Clustering (pHash/dHash)</div>
          <div class="step" id="step-places"><span class="step-icon">○</span> 4. Offline Reverse Geocoding</div>
          <div class="step" id="step-bursts"><span class="step-icon">○</span> 5. Burst Identification & Best Shot</div>
          <div class="step" id="step-groups"><span class="step-icon">○</span> 6. Event & Timeline Grouping</div>
          <div class="step" id="step-persons"><span class="step-icon">○</span> 7. Face Recognition & Person Clustering</div>
          <div class="step" id="step-index"><span class="step-icon">○</span> 8. Search Index Update</div>
        </div>
      </div>

      <p style="font-size:11px;color:var(--dim);margin:10px 0 0">Scans once and cleanly terminates. Zero persistent background CPU.</p>
    </div>

    <div class="card">
      <h3>Search & Filters</h3>
      <label>Text Query (Date, Place, Name)</label>
      <input type="text" id="filter-text" placeholder="e.g. 2024, Paris, trip">
      <label>Min Faces</label>
      <input type="number" id="filter-faces" min="0" placeholder="0">
      <label>Sort By</label>
      <select id="filter-sort">
        <option value="date">Date (Oldest first)</option>
        <option value="date_desc">Date (Newest first)</option>
        <option value="quality">Quality Score</option>
        <option value="path">Path Name</option>
      </select>
      <label>Duplicates</label>
      <select id="filter-dup">
        <option value="">All</option>
        <option value="none">Unique (Exclude Duplicates)</option>
        <option value="exact">Exact Duplicates</option>
        <option value="near">Near Duplicates</option>
      </select>
      <button onclick="loadSearch()" style="width:100%">Apply Search</button>
    </div>

    <div class="card">
      <h3>System & Health</h3>
      <div style="display:flex;gap:8px;">
        <button class="sec" onclick="loadDoctor()" style="flex:1">Doctor</button>
        <button class="sec" onclick="loadStats()" style="flex:1">Stats</button>
        <button class="sec" onclick="loadFailures()" style="flex:1;background:#381c1c;color:#f85149;">Errors (<span id="fail-count">0</span>)</button>
      </div>
      <div id="diag-out" style="margin-top:12px;"></div>
    </div>
  </div>

  <!-- Right Results Gallery -->
  <div>
    <!-- People Cluster Carousel -->
    <div class="card" id="people-card" style="display:none;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <h3 style="margin:0">People & Faces (<span id="people-count">0</span>)</h3>
        <span style="font-size:11px;color:var(--dim);">Click a person to filter photos, or double-click name to rename</span>
      </div>
      <div id="people-bar" class="people-bar"></div>
    </div>

    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <h3 style="margin:0">Library Items (<span id="result-count">0</span>)</h3>
        <button class="sec" onclick="loadSearch()">Refresh</button>
      </div>
      <div style="margin-top:16px;" id="gallery" class="gallery"></div>
    </div>
  </div>
</div>

<script>
let pollInterval = null;

async function api(endpoint, params = {}) {
  const url = new URL('/api/' + endpoint, window.location.origin);
  Object.keys(params).forEach(k => {
    if (params[k] !== null && params[k] !== undefined && params[k] !== '') {
      url.searchParams.append(k, params[k]);
    }
  });
  const res = await fetch(url);
  return res.json();
}

function setStatus(msg) {
  document.getElementById('status-bar').innerHTML = 'Status: ' + msg;
}

function updateStepStatus(stage) {
  const stages = ['scan', 'process', 'duplicates', 'places', 'bursts', 'groups', 'persons', 'index'];
  const stageIdx = stages.indexOf(stage);

  stages.forEach((s, idx) => {
    const el = document.getElementById('step-' + s);
    if (!el) return;
    const icon = el.querySelector('.step-icon');
    if (idx < stageIdx) {
      el.className = 'step done';
      icon.textContent = '✓';
    } else if (idx === stageIdx) {
      el.className = 'step active';
      icon.textContent = '▶';
    } else {
      el.className = 'step';
      icon.textContent = '○';
    }
  });
}

function resetSteps() {
  ['scan', 'process', 'duplicates', 'places', 'bursts', 'groups', 'persons', 'index'].forEach(s => {
    const el = document.getElementById('step-' + s);
    if (el) {
      el.className = 'step';
      el.querySelector('.step-icon').textContent = '○';
    }
  });
}

async function startRescan() {
  const path = document.getElementById('scan-path').value.trim();
  document.getElementById('btn-rescan').disabled = true;
  document.getElementById('btn-cancel').style.display = 'inline-block';
  document.getElementById('progress-box').style.display = 'block';
  document.getElementById('prog-bar').style.width = '0%';
  resetSteps();

  setStatus('Starting on-demand rescan...');
  await api('rescan_start', { path: path || '' });

  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollProgress, 250);
}

async function cancelRescan() {
  setStatus('Cancelling rescan...');
  await api('rescan_cancel');
}

async function pollProgress() {
  const prog = await api('progress');
  
  if (prog.stage) {
    document.getElementById('prog-stage').textContent = 'Stage: ' + prog.stage.toUpperCase();
    updateStepStatus(prog.stage);
  }

  if (prog.total && prog.total > 0) {
    const pct = Math.min(100, Math.round((prog.done / prog.total) * 100));
    document.getElementById('prog-bar').style.width = pct + '%';
    document.getElementById('prog-count').textContent = `${prog.done} / ${prog.total} (${pct}%)`;
  } else if (prog.done) {
    document.getElementById('prog-count').textContent = `${prog.done} item(s)`;
  }

  if (prog.current) {
    document.getElementById('prog-current').textContent = 'File: ' + prog.current;
  } else if (prog.message) {
    document.getElementById('prog-current').textContent = prog.message;
  }

  if (!prog.running) {
    clearInterval(pollInterval);
    pollInterval = null;
    document.getElementById('btn-rescan').disabled = false;
    document.getElementById('btn-cancel').style.display = 'none';
    
    if (prog.error) {
      setStatus('Error: ' + prog.error);
    } else {
      setStatus(`Rescan complete! Processed ${prog.summary?.processed || 0} new photo(s), ${prog.summary?.failed || 0} failed.`);
      // Mark all steps done
      document.querySelectorAll('.step').forEach(el => {
        el.className = 'step done';
        el.querySelector('.step-icon').textContent = '✓';
      });
      document.getElementById('prog-bar').style.width = '100%';
    }
    loadPersons();
    loadSearch();
  }
}

let selectedPersonId = null;

async function loadPersons() {
  try {
    const list = await api('persons');
    const bar = document.getElementById('people-bar');
    const card = document.getElementById('people-card');
    if (!list || !list.length) {
      card.style.display = 'none';
      return;
    }
    card.style.display = 'block';
    document.getElementById('people-count').textContent = list.length;
    bar.innerHTML = '';

    // "All People" reset button
    const allBtn = document.createElement('div');
    allBtn.className = 'person-pill' + (selectedPersonId === null ? ' active' : '');
    allBtn.innerHTML = `<div><div class="person-name">All Photos</div><div class="person-count">Reset filter</div></div>`;
    allBtn.onclick = () => {
      selectedPersonId = null;
      loadPersons();
      loadSearch();
    };
    bar.appendChild(allBtn);

    for (const p of list) {
      const pill = document.createElement('div');
      pill.className = 'person-pill' + (selectedPersonId === p.id ? ' active' : '');
      const avatarSrc = p.cover_face_id ? `/face_thumb?face_id=${p.cover_face_id}` : (p.cover_image_id ? `/thumb?id=${p.cover_image_id}` : '');
      pill.innerHTML = `
        <img class="person-avatar" src="${avatarSrc}" onerror="this.style.display='none'">
        <div>
          <div class="person-name" title="Double click to rename" id="pname-${p.id}">${p.name}</div>
          <div class="person-count">${p.image_count} photo(s)</div>
        </div>
      `;
      pill.onclick = (e) => {
        if (e.target.tagName === 'INPUT') return;
        selectedPersonId = (selectedPersonId === p.id) ? null : p.id;
        loadPersons();
        loadSearch();
      };
      pill.ondblclick = (e) => {
        e.stopPropagation();
        const newName = prompt('Rename person:', p.name);
        if (newName && newName.trim()) {
          api('rename_person', { id: p.id, name: newName.trim() }).then(() => {
            loadPersons();
          });
        }
      };
      bar.appendChild(pill);
    }
  } catch (err) {
    console.error('loadPersons error:', err);
  }
}

async function loadSearch() {
  setStatus('Loading images...');
  const params = {
    text: document.getElementById('filter-text').value,
    min_faces: document.getElementById('filter-faces').value,
    sort: document.getElementById('filter-sort').value,
    duplicate: document.getElementById('filter-dup').value
  };
  if (selectedPersonId !== null) {
    params.person_id = selectedPersonId;
  }
  const res = await api('search', params);
  document.getElementById('result-count').textContent = res.length;
  const gallery = document.getElementById('gallery');
  gallery.innerHTML = '';
  
  for (const item of res) {
    const card = document.createElement('div');
    card.className = 'item';
    
    let boxesHtml = '';
    if (item.faces && item.faces.length && item.width && item.height) {
      // Calculate letterbox/pillarbox offset for object-fit: contain inside 4/3 aspect-ratio box
      const wrapAspect = 4 / 3;
      const imgAspect = item.width / item.height;
      let renderedW = 100;
      let renderedH = 100;
      let offsetX = 0;
      let offsetY = 0;

      if (imgAspect > wrapAspect) {
        // Letterboxed top and bottom
        renderedH = (wrapAspect / imgAspect) * 100;
        offsetY = (100 - renderedH) / 2;
      } else {
        // Pillarboxed left and right
        renderedW = (imgAspect / wrapAspect) * 100;
        offsetX = (100 - renderedW) / 2;
      }

      for (const f of item.faces) {
        const l = (offsetX + (f.x / item.width) * renderedW).toFixed(2);
        const t = (offsetY + (f.y / item.height) * renderedH).toFixed(2);
        const w = ((f.w / item.width) * renderedW).toFixed(2);
        const h = ((f.h / item.height) * renderedH).toFixed(2);
        boxesHtml += `<div class="box" style="left:${l}%;top:${t}%;width:${w}%;height:${h}%;" title="Face confidence: ${(f.confidence*100).toFixed(0)}%"></div>`;
      }
    }

    card.innerHTML = `
      <div class="thumb-wrap">
        <img src="/thumb?id=${item.id}" alt="${item.path}" loading="lazy">
        ${boxesHtml}
      </div>
      <div class="meta">
        <b title="${item.path}">${item.path.split(/[\\/]/).pop()}</b>
        <div>${item.effective_ts || 'No Date'}</div>
        <div>
          <span class="badge">Faces: ${item.face_count || 0}</span>
          ${item.quality ? `<span class="badge">Q: ${Math.round(item.quality)}</span>` : ''}
          ${item.place ? `<span class="badge">${item.place}</span>` : ''}
        </div>
      </div>
    `;
    gallery.appendChild(card);
  }
  setStatus('Ready.');
}

async function loadDoctor() {
  const d = await api('doctor');
  document.getElementById('diag-out').innerHTML = '<pre>' + JSON.stringify(d, null, 2) + '</pre>';
}

async function loadStats() {
  const s = await api('stats');
  document.getElementById('diag-out').innerHTML = '<pre>' + JSON.stringify(s, null, 2) + '</pre>';
}

async function loadFailures() {
  const f = await api('failed');
  document.getElementById('fail-count').textContent = f.length;
  if (!f.length) {
    document.getElementById('diag-out').innerHTML = '<div style="color:#3fb950;font-size:12px;padding:8px;">No failed files! All processed successfully.</div>';
  } else {
    let html = '<div style="max-height:220px;overflow:auto;font-size:11px;background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:8px;">';
    f.forEach(item => {
      html += `<div style="margin-bottom:8px;border-bottom:1px solid #21262d;padding-bottom:4px;">
        <b style="color:#f85149;">${item.path.split(/[\\/]/).pop()}</b><br>
        <span style="color:var(--dim);">${item.path}</span><br>
        <code style="color:#e6edf3;">${item.error || 'Unknown error'}</code>
      </div>`;
    });
    html += '</div>';
    document.getElementById('diag-out').innerHTML = html;
  }
}

window.onload = () => {
  loadPersons();
  loadSearch();
  api('failed').then(f => {
    document.getElementById('fail-count').textContent = f.length;
  }).catch(() => {});
};
</script>
</body>
</html>
"""
