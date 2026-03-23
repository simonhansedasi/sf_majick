// csv.js — CSV import and calibration from real Salesforce exports

const csvData = { opps: null, users: null, leads: null };
let csvFitted = null;

// ── Column aliases (mirrors OrgCalibrator._normalise_opps) ───────
const COL_ALIASES = {
  stage:        ['stagename','stage','stage_name'],
  amount:       ['amount','amount__c','acv','arr','deal_value','revenue'],
  close_date:   ['closedate','close_date','closed_date'],
  created_date: ['createddate','created_date','createdate'],
  owner_id:     ['ownerid','owner_id','assigned_to','salesrep'],
  account_id:   ['accountid','account_id'],
};

const SF_STAGE_MAP = {
  'prospecting':           'Prospecting',
  'qualification':         'Qualification',
  'needs analysis':        'Qualification',
  'value proposition':     'Proposal',
  'id. decision makers':   'Proposal',
  'perception analysis':   'Proposal',
  'proposal/price quote':  'Proposal',
  'proposal':              'Proposal',
  'negotiation/review':    'Negotiation',
  'negotiation':           'Negotiation',
  'closed won':            'Closed Won',
  'closed lost':           'Closed Lost',
};

// ── CSV parser ───────────────────────────────────────────────────
function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const headers = splitLine(lines[0]).map(h => h.replace(/^"|"$/g,'').toLowerCase().trim());
  return lines.slice(1).filter(l => l.trim()).map(line => {
    const vals = splitLine(line);
    const row  = {};
    headers.forEach((h, i) => { row[h] = (vals[i]||'').replace(/^"|"$/g,'').trim(); });
    return row;
  });
}

function splitLine(line) {
  const out = []; let cur = ''; let inQ = false;
  for (const c of line) {
    if (c === '"') { inQ = !inQ; }
    else if (c === ',' && !inQ) { out.push(cur); cur = ''; }
    else cur += c;
  }
  out.push(cur);
  return out;
}

function detectCol(headers, key) {
  const aliases = COL_ALIASES[key] || [key];
  for (const a of aliases) {
    const m = headers.find(h => h === a || h.replace(/[\s_]/g,'') === a.replace(/[\s_]/g,''));
    if (m) return m;
  }
  return null;
}

// ── File loading ─────────────────────────────────────────────────
function loadCsv(type, input) {
  const file = (input.files || input)[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const rows = parseCsv(e.target.result);
    if (!rows.length) { alert('Could not parse — check the file format.'); return; }
    csvData[type] = rows;
    const zone  = document.getElementById('drop-' + type);
    const label = document.getElementById('drop-' + type + '-label');
    zone.classList.add('loaded');
    label.textContent = '✓ ' + file.name + ' — ' + rows.length.toLocaleString() + ' rows';
    if (type === 'opps') showColMapping(rows);
    checkShowFitButton();
  };
  reader.readAsText(file);
}

// Drag and drop
['opps','users','leads'].forEach(type => {
  const zone = document.getElementById('drop-' + type);
  if (!zone) return;
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    loadCsv(type, e.dataTransfer.files);
  });
});

function showColMapping(rows) {
  const headers = Object.keys(rows[0]);
  document.getElementById('col-mapping-panel').style.display = 'block';

  const fieldLabels = {
    stage: 'Stage column', amount: 'Deal amount', close_date: 'Close date',
    created_date: 'Created date', owner_id: 'Owner / rep ID', account_id: 'Account ID',
  };
  const opts = ['(none)', ...headers].map(h => `<option value="${h}">${h}</option>`).join('');
  document.getElementById('col-mapping-grid').innerHTML = Object.entries(fieldLabels).map(([key, label]) => {
    const det = detectCol(headers, key) || '';
    return `<div class="map-row" style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <span style="font-size:13px;color:var(--text2);width:150px;flex-shrink:0">${label}</span>
      <select id="map-${key}">
        ${ ['(none)', ...headers].map(h => `<option value="${h}"${h===det?' selected':''}>${h}</option>`).join('') }
      </select>
      ${det
        ? `<span style="font-size:11px;color:var(--text3)">auto</span>`
        : `<span style="font-size:11px;color:var(--amber)">not found</span>`}
    </div>`;
  }).join('');
}

function getColMap() {
  const keys = ['stage','amount','close_date','created_date','owner_id','account_id'];
  const map  = {};
  for (const k of keys) {
    const el = document.getElementById('map-' + k);
    if (el && el.value !== '(none)') map[k] = el.value;
  }
  return map;
}

function checkShowFitButton() {
  document.getElementById('csv-fit-row').style.display = csvData.opps ? 'block' : 'none';
}

// ── Calibration (mirrors OrgCalibrator.calibrate()) ──────────────
function calibrateFromCsv() {
  const opps  = csvData.opps;
  const users = csvData.users;
  const leads = csvData.leads;
  const cmap  = getColMap();
  const warnings = [];

  function colVal(row, key) {
    const c = cmap[key];
    return c ? row[c] : undefined;
  }

  // Normalise rows
  const rows = opps.map(r => ({
    stage_sim:    SF_STAGE_MAP[(colVal(r,'stage')||'').toLowerCase().trim()] || null,
    amount:       parseFloat(colVal(r,'amount')) || null,
    close_date:   colVal(r,'close_date')   ? new Date(colVal(r,'close_date'))   : null,
    created_date: colVal(r,'created_date') ? new Date(colVal(r,'created_date')) : null,
    owner:        colVal(r,'owner_id')  || null,
    account:      colVal(r,'account_id')|| null,
  }));

  if (!cmap.stage) warnings.push({ level:'warn', msg:'No stage column detected — stage-based fitting skipped.' });

  // Team size
  let n_reps = null;
  if (users && users.length) {
    n_reps = users.length;
  } else {
    const owners = new Set(rows.map(r=>r.owner).filter(Boolean));
    if (owners.size) n_reps = owners.size;
    else warnings.push({ level:'warn', msg:'No owner column — rep count defaulted.' });
  }

  // Accounts
  const acctSet = new Set(rows.map(r=>r.account).filter(Boolean));
  const n_seed_accounts = acctSet.size || rows.length;

  // Win / lost rates
  const staged  = rows.filter(r => r.stage_sim);
  const closed  = staged.filter(r => r.stage_sim === 'Closed Won' || r.stage_sim === 'Closed Lost');
  const nWon    = closed.filter(r => r.stage_sim === 'Closed Won').length;
  const nLost   = closed.filter(r => r.stage_sim === 'Closed Lost').length;
  const nClosed = closed.length;

  if (staged.length === 0 && cmap.stage)
    warnings.push({ level:'error', msg:'Stage column found but no rows matched known SF stage names. Check column mapping.' });
  if (nClosed < 10)
    warnings.push({ level:'warn', msg:`Only ${nClosed} closed deals — win rate estimate may be noisy. 20+ recommended.` });

  const win_rate  = nClosed > 0 ? nWon  / nClosed : null;
  const lost_rate = nClosed > 0 ? nLost / nClosed : null;

  // Cycle time (median)
  const cyclePairs = rows.filter(r => r.close_date && r.created_date && r.close_date > r.created_date);
  let avg_cycle = null;
  if (cyclePairs.length) {
    const days = cyclePairs.map(r => (r.close_date - r.created_date) / 86400000).filter(d => d > 0).sort((a,b)=>a-b);
    avg_cycle = days[Math.floor(days.length / 2)];
  } else {
    warnings.push({ level:'warn', msg:'No close_date / created_date columns — cycle time not fitted.' });
  }

  const cycle = avg_cycle || 60;
  const base_prob_close = win_rate  != null ? +clamp(win_rate,  0.01, 0.60).toFixed(4) : null;
  const base_prob_lost  = lost_rate != null ? +clamp(lost_rate / Math.max(cycle, 1), 0.001, 0.10).toFixed(5) : null;
  const inactivity_alpha = +clamp(0.010 * (45 / Math.max(cycle, 10)), 0.002, 0.025).toFixed(5);
  const stagnation_alpha = +clamp(0.008 * (45 / Math.max(cycle, 10)), 0.001, 0.020).toFixed(5);

  // Stage advancement rates
  const STO = ['Prospecting','Qualification','Proposal','Negotiation'];
  function advRate(stage) {
    const idx = STO.indexOf(stage);
    const atOrPast = staged.filter(r => {
      const ri = STO.indexOf(r.stage_sim);
      return ri >= idx || r.stage_sim === 'Closed Won' || r.stage_sim === 'Closed Lost';
    }).length;
    const past = staged.filter(r => {
      const ri = STO.indexOf(r.stage_sim);
      return ri > idx || r.stage_sim === 'Closed Won' || r.stage_sim === 'Closed Lost';
    }).length;
    return atOrPast > 0 ? past / atOrPast : null;
  }
  const avgDaysByStage = { Prospecting:25, Qualification:20, Proposal:15, Negotiation:12 };
  function toDaily(stage, rate) {
    return rate != null ? +clamp(rate / avgDaysByStage[stage], 0.001, 0.30).toFixed(4) : null;
  }

  const prospAdv = advRate('Prospecting');
  const qualAdv  = advRate('Qualification');
  const propAdv  = advRate('Proposal');
  const negAdv   = advRate('Negotiation');

  // Revenue lognormal params
  const amounts = rows.map(r=>r.amount).filter(a => a && a > 0);
  let rev_mu = null, rev_sigma = null, dealStats = null;
  if (amounts.length >= 5) {
    const logs = amounts.map(a => Math.log(a));
    const mu   = logs.reduce((s,v)=>s+v,0) / logs.length;
    const sig  = Math.sqrt(logs.map(v=>(v-mu)**2).reduce((s,v)=>s+v,0) / logs.length);
    rev_mu    = +mu.toFixed(3);
    rev_sigma = +clamp(sig, 0.2, 2.5).toFixed(3);
    amounts.sort((a,b)=>a-b);
    dealStats = {
      p10:    amounts[Math.floor(amounts.length*0.10)],
      median: amounts[Math.floor(amounts.length/2)],
      p90:    amounts[Math.floor(amounts.length*0.90)],
      mean:   amounts.reduce((s,v)=>s+v,0)/amounts.length,
      n:      amounts.length,
    };
  } else {
    warnings.push({ level:'warn', msg:'No amount column or fewer than 5 valid values — revenue distribution not fitted.' });
  }

  // Lead conversion
  let base_prob_lead_conversion = null;
  if (leads && leads.length) {
    const hdr    = Object.keys(leads[0]);
    const convCol = hdr.find(k => ['isconverted','is_converted','converted'].includes(k.toLowerCase()));
    if (convCol) {
      const nConv = leads.filter(r => String(r[convCol]).toLowerCase() === 'true' || r[convCol] === '1').length;
      base_prob_lead_conversion = +clamp(nConv / leads.length, 0.01, 0.60).toFixed(4);
    }
  }

  const stageCounts = Object.fromEntries(
    [...STO,'Closed Won','Closed Lost'].map(s => [s, staged.filter(r=>r.stage_sim===s).length])
  );

  const fitted = {
    label: 'csv_fitted',
    n_reps: n_reps || 8,
    n_seed_accounts,
    days: 90,
    n_runs: 100,
    base_prob_close,
    base_prob_lost,
    base_prob_prospecting:    toDaily('Prospecting', prospAdv),
    base_prob_qualification:  toDaily('Qualification', qualAdv),
    base_prob_proposal:       toDaily('Proposal', propAdv),
    base_prob_negotiation:    toDaily('Negotiation', negAdv),
    base_prob_lead_conversion,
    inactivity_alpha,
    stagnation_alpha,
    apply_decay: true,
    notes: `CSV-fitted. ${rows.length} opps, ${nClosed} closed (${nWon} won / ${nLost} lost).`,
  };

  const observed = {
    n_opps: rows.length, nClosed, nWon, nLost,
    win_rate, lost_rate, avg_cycle, dealStats, stageCounts,
    rev_mu, rev_sigma,
    adv_rates: { Prospecting: prospAdv, Qualification: qualAdv, Proposal: propAdv, Negotiation: negAdv },
  };

  return { fitted, observed, warnings };
}

// ── Fit button handler ───────────────────────────────────────────
function fitFromCsv() {
  document.getElementById('csv-fit-status').textContent = 'Fitting…';
  setTimeout(() => {
    try {
      csvFitted = calibrateFromCsv();
      renderCsvResults(csvFitted);
      document.getElementById('csv-fit-status').textContent = 'Done';
    } catch(e) {
      document.getElementById('csv-fit-status').textContent = 'Error: ' + e.message;
      console.error(e);
    }
  }, 100);
}

// ── Render ───────────────────────────────────────────────────────
function renderCsvResults({ fitted, observed, warnings }) {
  document.getElementById('csv-fit-output').style.display = 'block';

  // Summary metrics
  document.getElementById('csv-summary').innerHTML = [
    { label:'Opportunities', value: observed.n_opps.toLocaleString(),                            sub:'total rows' },
    { label:'Closed won',    value: observed.nWon,                                               sub: observed.win_rate!=null ? 'win rate '+fmtPct(observed.win_rate) : '' },
    { label:'Avg cycle',     value: observed.avg_cycle!=null ? Math.round(observed.avg_cycle)+'d' : 'n/a', sub:'median days open' },
    { label:'Median deal',   value: observed.dealStats ? '$'+fmtK(observed.dealStats.median) : 'n/a', sub: observed.dealStats ? 'n='+observed.dealStats.n : 'no amount col' },
  ].map(m =>
    `<div class="metric"><div class="label">${m.label}</div><div class="value">${m.value}</div><div class="sub">${m.sub}</div></div>`
  ).join('');

  // Fitted fields
  const compareFields = [
    { key:'base_prob_close',          label:'Close rate',         def:0.15 },
    { key:'base_prob_lost',           label:'Lost rate (daily)',   def:0.035 },
    { key:'base_prob_prospecting',    label:'Prospecting adv.',    def:0.08 },
    { key:'base_prob_qualification',  label:'Qualification adv.',  def:0.04 },
    { key:'base_prob_proposal',       label:'Proposal adv.',       def:0.02 },
    { key:'base_prob_negotiation',    label:'Negotiation adv.',    def:0.01 },
    { key:'base_prob_lead_conversion',label:'Lead conversion',     def:0.25 },
    { key:'inactivity_alpha',         label:'Inactivity alpha',    def:0.010 },
    { key:'stagnation_alpha',         label:'Stagnation alpha',    def:0.008 },
  ];
  document.getElementById('csv-fit-fields').innerHTML = compareFields.map(f => {
    const v   = fitted[f.key];
    const pct = v != null ? (v - f.def) / Math.abs(f.def) : 0;
    const cls = v == null ? 'diff-same' : pct > 0.05 ? 'diff-up' : pct < -0.05 ? 'diff-dn' : 'diff-same';
    const disp = v == null
      ? '<span style="color:var(--text3)">not fitted</span>'
      : (f.key.includes('alpha') ? (v*100).toFixed(3)+'%' : fmtPct(v));
    return `<div class="fit-row">
      <span class="fit-key">${f.label}</span>
      <div class="fit-vals">
        <span class="fit-orig">θ: ${fmtPct(f.def)}</span>
        <span class="fit-fitted ${cls}">${disp}</span>
      </div>
    </div>`;
  }).join('');

  // Distributions
  const obs = observed;
  const distRows = [
    ['Win rate',        obs.win_rate!=null  ? fmtPct(obs.win_rate)  : 'n/a'],
    ['Lost rate',       obs.lost_rate!=null ? fmtPct(obs.lost_rate) : 'n/a'],
    ['Avg cycle',       obs.avg_cycle!=null ? Math.round(obs.avg_cycle)+' days' : 'n/a'],
  ];
  if (obs.dealStats) {
    distRows.push(
      ['Deal p10',  '$'+fmtK(obs.dealStats.p10)],
      ['Deal median','$'+fmtK(obs.dealStats.median)],
      ['Deal p90',  '$'+fmtK(obs.dealStats.p90)],
      ['Rev log-mean', obs.rev_mu?.toFixed(2) ?? 'n/a'],
      ['Rev log-sigma',obs.rev_sigma?.toFixed(2) ?? 'n/a'],
    );
  }
  for (const [s,r] of Object.entries(obs.adv_rates)) {
    distRows.push([s+' adv.', r!=null ? fmtPct(r) : 'n/a']);
  }
  document.getElementById('csv-distributions').innerHTML = distRows.map(([k,v]) =>
    `<div class="fit-row"><span class="fit-key">${k}</span><span class="fit-fitted">${v}</span></div>`
  ).join('');

  // Stage chart
  drawCsvStageChart(obs.stageCounts);

  // Warnings
  document.getElementById('csv-warnings').innerHTML = warnings.length === 0
    ? '<span style="font-size:13px;color:var(--green-dark)">✓ No issues detected</span>'
    : warnings.map(w => {
        const icon  = w.level === 'error' ? '✗' : '⚠';
        const color = w.level === 'error' ? 'var(--red)' : 'var(--amber)';
        return `<div class="warn-row">
          <span style="color:${color};flex-shrink:0">${icon}</span>
          <span style="font-size:13px">${w.msg}</span>
        </div>`;
      }).join('');

  // JSON
  const clean = { ...fitted };
  if (obs.rev_mu    != null) clean.rev_mu    = obs.rev_mu;
  if (obs.rev_sigma != null) clean.rev_sigma = obs.rev_sigma;
  document.getElementById('csv-fit-json').textContent = JSON.stringify(clean, null, 2);

  // Python
  document.getElementById('csv-fit-python').textContent = pythonSnippet('csv_fitted_config.json');
}

function drawCsvStageChart(stageCounts) {
  const canvas = document.getElementById('csv-stage-chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.offsetWidth || 400;
  const H   = 150;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const stages = ['Prospecting','Qualification','Proposal','Negotiation','Closed Won','Closed Lost'];
  const colors = ['#378ADD','#BA7517','#1D9E75','#7F77DD','#0F6E56','#E24B4A'];
  const vals   = stages.map(s => stageCounts[s] || 0);
  const maxVal = Math.max(...vals, 1);
  const barW   = (W - 20) / stages.length - 4;
  const isDark = matchMedia('(prefers-color-scheme: dark)').matches;
  const tc     = isDark ? 'rgba(200,190,170,0.6)' : 'rgba(60,60,50,0.6)';

  vals.forEach((v, i) => {
    const x    = 10 + i * ((W-20)/stages.length);
    const barH = (v / maxVal) * (H - 44);
    ctx.fillStyle = colors[i];
    ctx.beginPath(); ctx.roundRect(x, H-28-barH, barW, barH, 3); ctx.fill();
    ctx.fillStyle = tc;
    ctx.font = '10px -apple-system,sans-serif'; ctx.textAlign = 'center';
    if (v > 0) ctx.fillText(v, x+barW/2, H-30-barH-2);
    ctx.fillText(stages[i].split(' ')[0], x+barW/2, H-12);
  });
}

// ── Load into Setup ──────────────────────────────────────────────
function loadCsvIntoSetup() {
  if (!csvFitted) return;
  const { fitted, observed } = csvFitted;

  if (fitted.n_reps)                       setSlider('nreps',      fitted.n_reps);
  if (fitted.n_seed_accounts)              setSlider('accts',      fitted.n_seed_accounts);
  if (fitted.base_prob_close       != null) setSlider('close',      fitted.base_prob_close,       'pct');
  if (fitted.base_prob_lost        != null) setSlider('lost',       fitted.base_prob_lost,        'pct2');
  if (fitted.inactivity_alpha      != null) setSlider('inactivity', fitted.inactivity_alpha,      'dec3');
  if (fitted.stagnation_alpha      != null) setSlider('stagnation', fitted.stagnation_alpha,      'dec3');
  if (fitted.base_prob_prospecting != null) setSlider('p-prosp',    fitted.base_prob_prospecting, 'pct');
  if (fitted.base_prob_qualification!=null) setSlider('p-qual',     fitted.base_prob_qualification,'pct');
  if (fitted.base_prob_proposal    != null) setSlider('p-prop',     fitted.base_prob_proposal,    'pct');
  if (fitted.base_prob_negotiation != null) setSlider('p-neg',      fitted.base_prob_negotiation, 'pct');
  if (fitted.base_prob_lead_conversion!=null) setSlider('p-lead',   fitted.base_prob_lead_conversion,'pct');
  if (observed.rev_mu              != null) setSlider('rev-mu',     observed.rev_mu,              'dec1');
  if (observed.rev_sigma           != null) setSlider('rev-sig',    observed.rev_sigma,           'dec1');
  updateRevPreview();

  showTab('setup');
  const btn = event.target;
  btn.textContent = '✓ Loaded into Setup';
  setTimeout(() => btn.textContent = 'Load into Setup →', 2000);
}
