// ui.js — DOM interaction, sliders, rendering, tab management

let simData    = null;
let fittedData = null;

// ── Formatting helpers ───────────────────────────────────────────
function fmtK(v) {
  if (v >= 1e6) return (v/1e6).toFixed(1) + 'M';
  if (v >= 1e3) return (v/1e3).toFixed(0) + 'K';
  return Math.round(v).toString();
}
function fmtPct(v, dec=1) { return (v*100).toFixed(dec) + '%'; }

// ── Slider sync ──────────────────────────────────────────────────
function sync(el, valId, fmt) {
  const v  = parseFloat(el.value);
  const sp = document.getElementById(valId);
  if (!sp) return;
  switch (fmt) {
    case 'pct':  sp.textContent = Math.round(v*100) + '%'; break;
    case 'pct2': sp.textContent = (v*100).toFixed(1) + '%'; break;
    case 'dec1': sp.textContent = v.toFixed(1); break;
    case 'dec2': sp.textContent = v.toFixed(2); break;
    case 'dec3': sp.textContent = v.toFixed(3); break;
    case 'x':    sp.textContent = v.toFixed(2) + '×'; break;
    default:     sp.textContent = Math.round(v); break;
  }
  if (valId === 'v-rev-mu' || valId === 'v-rev-sig') updateRevPreview();
}

function setSlider(id, val, fmt) {
  const el = document.getElementById('s-' + id);
  if (!el) return;
  el.value = val;
  sync(el, 'v-' + id, fmt);
}

function updateRevPreview() {
  const mu  = parseFloat(document.getElementById('s-rev-mu').value);
  const sig = parseFloat(document.getElementById('s-rev-sig').value);
  const el  = document.getElementById('rev-preview');
  if (!el) return;
  el.textContent = 'p10 $' + fmtK(Math.exp(mu - sig*1.28))
    + '  ·  median $' + fmtK(Math.exp(mu))
    + '  ·  p90 $'    + fmtK(Math.exp(mu + sig*1.28));
}

// ── Config reader ────────────────────────────────────────────────
function getConfig() {
  function val(id)  { return parseFloat(document.getElementById('s-' + id).value); }
  function ival(id) { return parseInt(document.getElementById('s-' + id).value); }
  return {
    n_reps:   ival('nreps'), closer: val('closer'), nurturer: val('nurturer'),
    grinder:  val('grinder'), scattered: val('scattered'), comp_rate: val('comp'),
    n_accounts: ival('accts'), n_leads: ival('leads'), days: ival('days'),
    base_prob_close: val('close'), base_prob_lost: val('lost'),
    inactivity_alpha: val('inactivity'), stagnation_alpha: val('stagnation'),
    base_prob_prospecting:    val('p-prosp'),
    base_prob_qualification:  val('p-qual'),
    base_prob_proposal:       val('p-prop'),
    base_prob_negotiation:    val('p-neg'),
    base_prob_lead_conversion: val('p-lead'),
    sentiment_beta_opportunity: val('sent-opp'),
    sentiment_beta_lead:        val('sent-lead'),
    momentum_beta_opportunity:  val('mom-opp'),
    friction_beta_opportunity:  val('fric-opp'),
    rev_mu: val('rev-mu'), rev_sigma: val('rev-sig'),
    difficulty_mean: val('diff'), commission_rate: val('comm-rate'),
    p_skeptic: val('skeptic'), p_urgent: val('urgent'),
    p_price: val('price'), p_easy: val('easy'),
  };
}

// ── Defaults ─────────────────────────────────────────────────────
const DEFAULTS = {
  nreps:8, closer:0.30, nurturer:0.25, grinder:0.30, scattered:0.15, comp:1.0,
  accts:10, leads:4, days:90,
  close:0.15, lost:0.035, inactivity:0.010, stagnation:0.008,
  'p-prosp':0.08, 'p-qual':0.04, 'p-prop':0.02, 'p-neg':0.01, 'p-lead':0.25,
  'sent-opp':0.20, 'sent-lead':0.10, 'mom-opp':0.75, 'fric-opp':0.50,
  'rev-mu':10.82, 'rev-sig':0.8, diff:0.06, 'comm-rate':0.08,
  skeptic:0.30, urgent:0.40, price:0.20, easy:0.10,
};
const DFMT = {
  closer:'pct', nurturer:'pct', grinder:'pct', scattered:'pct', comp:'x',
  close:'pct', lost:'pct2', inactivity:'dec3', stagnation:'dec3',
  'p-prosp':'pct','p-qual':'pct','p-prop':'pct','p-neg':'pct','p-lead':'pct',
  'sent-opp':'dec2','sent-lead':'dec2','mom-opp':'dec2','fric-opp':'dec2',
  'rev-mu':'dec1','rev-sig':'dec1', diff:'dec2','comm-rate':'pct',
  skeptic:'pct', urgent:'pct', price:'pct', easy:'pct',
};

function resetDefaults() {
  for (const [id, v] of Object.entries(DEFAULTS)) setSlider(id, v, DFMT[id]);
  updateRevPreview();
}

// ── Randomize ────────────────────────────────────────────────────
function randomizeAll() {
  const w = [Math.random(),Math.random(),Math.random(),Math.random()];
  const tot = w.reduce((a,b)=>a+b,0);
  const [c,n,g,s] = w.map(x => Math.round(x/tot*20)/20);
  setSlider('nreps',    randInt(4, 18));
  setSlider('closer',   clamp(c, 0, 0.95), 'pct');
  setSlider('nurturer', clamp(n, 0, 0.95), 'pct');
  setSlider('grinder',  clamp(g, 0, 0.95), 'pct');
  setSlider('scattered',clamp(s, 0, 0.95), 'pct');
  setSlider('comp',     +(Math.round(rand(0.8,1.4)*20)/20).toFixed(2), 'x');
  setSlider('accts',    randInt(5, 30));
  setSlider('leads',    randInt(0, 15));
  setSlider('days',     Math.round(rand(4, 24)) * 15);
  setSlider('close',    +(Math.round(rand(8, 35))/100).toFixed(2), 'pct');
  setSlider('lost',     +(Math.round(rand(5, 80))/1000).toFixed(3), 'pct2');
  setSlider('inactivity', +(rand(0.003,0.030)).toFixed(3), 'dec3');
  setSlider('stagnation', +(rand(0.002,0.025)).toFixed(3), 'dec3');
  setSlider('p-prosp',  +(rand(0.02,0.18)).toFixed(3), 'pct');
  setSlider('p-qual',   +(rand(0.01,0.12)).toFixed(3), 'pct');
  setSlider('p-prop',   +(rand(0.005,0.08)).toFixed(3), 'pct');
  setSlider('p-neg',    +(rand(0.002,0.05)).toFixed(3), 'pct');
  setSlider('p-lead',   +(rand(0.05,0.50)).toFixed(2), 'pct');
  setSlider('sent-opp', +(rand(0.05,0.60)).toFixed(2), 'dec2');
  setSlider('sent-lead',+(rand(0.02,0.40)).toFixed(2), 'dec2');
  setSlider('mom-opp',  +(rand(0.20,1.50)).toFixed(2), 'dec2');
  setSlider('fric-opp', +(rand(0.10,1.20)).toFixed(2), 'dec2');
  const mus = [9.21, 10.13, 10.82, 11.51, 12.21];
  setSlider('rev-mu',  mus[randInt(0, mus.length-1)], 'dec1');
  setSlider('rev-sig', +(rand(0.4, 1.6)).toFixed(1), 'dec1');
  setSlider('diff',    +(rand(0.02,0.14)).toFixed(2), 'dec2');
  setSlider('comm-rate',+(rand(0.04,0.15)).toFixed(2), 'pct');
  const pw = [Math.random(),Math.random(),Math.random(),Math.random()];
  const pt = pw.reduce((a,b)=>a+b,0);
  setSlider('skeptic', clamp(Math.round(pw[0]/pt*20)/20,0,0.9),'pct');
  setSlider('urgent',  clamp(Math.round(pw[1]/pt*20)/20,0,0.9),'pct');
  setSlider('price',   clamp(Math.round(pw[2]/pt*20)/20,0,0.9),'pct');
  setSlider('easy',    clamp(Math.round(pw[3]/pt*20)/20,0,0.9),'pct');
  updateRevPreview();
}

// ── Run simulation ───────────────────────────────────────────────
function runSim() {
  simData = runSimulation(getConfig());
  renderSimResults(simData);
  document.getElementById('fitter-empty').style.display    = 'none';
  document.getElementById('fitter-content').style.display = 'block';
  document.getElementById('fit-output').style.display     = 'none';
  document.getElementById('fit-status').textContent        = '';
  showTab('sim');
}

function renderSimResults(d) {
  document.getElementById('sim-empty').style.display   = 'none';
  document.getElementById('sim-results').style.display = 'block';

  // Metrics
  document.getElementById('sim-metrics').innerHTML = [
    { label:'Closed won',  value: d.won.length,                                    sub:`of ${d.opps.length} opps` },
    { label:'Win rate',    value: d.winRate!=null ? fmtPct(d.winRate,0) : 'n/a',   sub:`${d.closed.length} closed` },
    { label:'Won revenue', value: d.wonRevenue>0 ? '$'+fmtK(d.wonRevenue) : '$0',  sub:'total' },
    { label:'Avg cycle',   value: d.avgCycleDays!=null ? Math.round(d.avgCycleDays)+'d' : 'n/a', sub:'days to close' },
  ].map(m =>
    `<div class="metric"><div class="label">${m.label}</div><div class="value">${m.value}</div><div class="sub">${m.sub}</div></div>`
  ).join('');

  // Reps
  document.getElementById('rep-list').innerHTML = d.reps.map(r => {
    const burnPct = Math.min(100, (r.stress / r.burnout) * 100).toFixed(0);
    return `<div class="rep-row">
      <span class="badge badge-${r.arch}">${r.arch}</span>
      <span style="font-size:12px;color:var(--text2)">${r.id}</span>
      <span style="margin-left:auto;font-size:12px;color:var(--text2)">W:${r.wins} L:${r.losses}</span>
      <div class="stress-bar" title="Stress ${burnPct}%"><div class="stress-fill" style="width:${burnPct}%"></div></div>
      <span style="font-size:12px;color:var(--text3);min-width:40px;text-align:right">$${fmtK(r.earnings)}</span>
    </div>`;
  }).join('');

  // Stage bars
  const total = d.opps.length || 1;
  document.getElementById('stage-bars').innerHTML = ALL_STAGES.map(s => {
    const n = d.stageCount[s] || 0;
    return `<div class="bar-row">
      <span class="bar-label">${s}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${(n/total*100).toFixed(0)}%;background:${STAGE_COLORS[s]}"></div></div>
      <span class="bar-val">${n}</span>
    </div>`;
  }).join('');

  // Opp sample
  const sample = [...d.opps].sort(() => Math.random()-0.5).slice(0, 20);
  document.getElementById('opp-table').innerHTML = sample.map(o => {
    const key = o.stage.replace(/ /g,'');
    const sColor = o.sentiment > 0.1 ? 'var(--green)' : o.sentiment < -0.1 ? 'var(--red)' : 'var(--text3)';
    return `<div class="opp-row">
      <span style="flex:1">${o.name}</span>
      <span style="font-size:10px;color:var(--text3)">${(o.personality||'').split(' ')[0]}</span>
      <span class="stage-pill s-${key}">${o.stage}</span>
      <span style="min-width:72px;text-align:right;color:var(--text2)">$${fmtK(o.revenue)}</span>
      <span style="min-width:52px;text-align:right;font-size:12px;color:${sColor}">s:${o.sentiment.toFixed(2)}</span>
    </div>`;
  }).join('');

  // Chart
  requestAnimationFrame(() => drawActivityChart(d.dayStats));
}

function drawActivityChart(dayStats) {
  const canvas = document.getElementById('activity-chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.offsetWidth || 600;
  const H   = 180;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const recent = dayStats.slice(-30);
  const maxActs = Math.max(...recent.map(d=>d.actions), 1);
  const barW    = (W - 20) / recent.length;
  const isDark  = matchMedia('(prefers-color-scheme: dark)').matches;

  recent.forEach((d, i) => {
    const x    = 10 + i * barW;
    const barH = (d.actions / maxActs) * (H - 40);
    if (d.isWeekend) {
      ctx.fillStyle = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)';
      ctx.fillRect(x, 8, barW, H - 28);
    }
    ctx.fillStyle = isDark ? 'rgba(150,140,120,0.25)' : 'rgba(60,60,50,0.12)';
    if (barH > 0) { ctx.beginPath(); ctx.roundRect(x+1, H-20-barH, barW-3, barH, 2); ctx.fill(); }
    if (d.won > 0) {
      ctx.fillStyle = '#1D9E75';
      ctx.beginPath(); ctx.arc(x + barW/2, H-22-barH, 3, 0, Math.PI*2); ctx.fill();
    }
  });

  ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  ctx.lineWidth = 0.5;
  ctx.beginPath(); ctx.moveTo(8, 8); ctx.lineTo(8, H-18); ctx.lineTo(W-2, H-18); ctx.stroke();
  ctx.fillStyle = isDark ? 'rgba(200,190,170,0.4)' : 'rgba(80,80,70,0.4)';
  ctx.font = '10px -apple-system,sans-serif'; ctx.textAlign = 'center';
  ctx.fillText('Daily micro actions (last 30 days) — green dot = Closed Won', W/2, H-4);
}

// ── Org fitter ───────────────────────────────────────────────────
function fitOrg() {
  if (!simData) return;
  document.getElementById('fit-status').textContent = 'Fitting…';
  setTimeout(() => {
    fittedData = calibrateFromSim(simData);
    renderFitResults(fittedData, simData);
    document.getElementById('fit-output').style.display = 'block';
    document.getElementById('fit-status').textContent   = 'Done';
  }, 150);
}

function renderFitResults(fitted, data) {
  const compareFields = [
    { key:'base_prob_close',          label:'Close rate',         def:0.15 },
    { key:'base_prob_lost',           label:'Lost rate (daily)',   def:0.035 },
    { key:'base_prob_prospecting',    label:'Prospecting adv.',    def:0.08 },
    { key:'base_prob_qualification',  label:'Qualification adv.',  def:0.04 },
    { key:'base_prob_proposal',       label:'Proposal adv.',       def:0.02 },
    { key:'inactivity_alpha',         label:'Inactivity alpha',    def:0.010 },
    { key:'stagnation_alpha',         label:'Stagnation alpha',    def:0.008 },
  ];

  function fv(v, def) {
    if (v == null) return '<span style="color:var(--text3)">not fitted</span>';
    if (def < 0.1) return (v*100).toFixed(3) + '%';
    return fmtPct(v);
  }

  document.getElementById('fit-fields').innerHTML = compareFields.map(f => {
    const v   = fitted[f.key];
    const pct = v != null ? (v - f.def) / Math.abs(f.def) : 0;
    const cls = v == null ? 'diff-same' : pct > 0.05 ? 'diff-up' : pct < -0.05 ? 'diff-dn' : 'diff-same';
    return `<div class="fit-row">
      <span class="fit-key">${f.label}</span>
      <div class="fit-vals">
        <span class="fit-orig">θ default: ${fmtPct(f.def)}</span>
        <span class="fit-fitted ${cls}">${fv(v, f.def)}</span>
      </div>
    </div>`;
  }).join('');

  const obs = fitted._observed || {};
  document.getElementById('fit-validation').innerHTML = [
    ['Opps simulated',    data.opps.length],
    ['Closed won',        data.won.length],
    ['Closed lost',       data.lost.length],
    ['Win rate',          obs.win_rate!=null ? obs.win_rate+'%' : 'n/a'],
    ['Avg cycle',         obs.avg_cycle_days!=null ? obs.avg_cycle_days+' days' : 'n/a'],
    ['Avg deal size',     obs.avg_deal_size!=null ? '$'+fmtK(obs.avg_deal_size) : 'n/a'],
    ['Total actions',     obs.total_actions?.toLocaleString() ?? '—'],
  ].map(([k,v]) =>
    `<div class="fit-row"><span class="fit-key">${k}</span><span class="fit-fitted">${v}</span></div>`
  ).join('');

  const clean = {...fitted};
  delete clean._observed;
  document.getElementById('fit-json').textContent = JSON.stringify(clean, null, 2);

  document.getElementById('fit-python').textContent = pythonSnippet('fitted_config.json');
}

// ── Export helpers ───────────────────────────────────────────────
function copyEl(id) {
  const txt = document.getElementById(id).textContent;
  navigator.clipboard.writeText(txt).then(() => {
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 1500);
  });
}

function downloadEl(id, filename) {
  const txt  = document.getElementById(id).textContent;
  const blob = new Blob([txt], { type:'application/json' });
  const a    = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: filename });
  a.click();
  URL.revokeObjectURL(a.href);
}

function pythonSnippet(filename) {
  return `from sf_majick.sim.org_config import OrgConfig
from sf_majick.sim.org_calibrator import ExperimentRunner, build_state_from_config
from sf_majick.sim.simulate import run_simulation
from sf_majick.sim.micro_policy import simulate_rep_thinking

cfg = OrgConfig.load("${filename}")
print(cfg.describe())

runner = ExperimentRunner(
    base_config   = cfg,
    state_factory = build_state_from_config,
    sim_fn        = run_simulation,
    micro_policy  = simulate_rep_thinking,
    n_iterations  = 200,
)

results = runner.compare({
    "baseline":         {},
    "hire_2_closers":   {"n_reps": cfg.n_reps + 2},
    "coaching":         {"base_prob_close": (cfg.base_prob_close or 0.15) + 0.05},
    "pipeline_hygiene": {
        "inactivity_alpha": (cfg.inactivity_alpha or 0.010) * 0.6,
        "stagnation_alpha": (cfg.stagnation_alpha or 0.008) * 0.6,
    },
})

print(results.groupby("label")[["won_rate","revenue_per_run","avg_rep_earnings"]].mean())`;
}

// ── Tabs ─────────────────────────────────────────────────────────
function showTab(name) {
  const tabs = ['setup','sim','fitter','csv'];
  tabs.forEach((t, i) => {
    document.getElementById('tab-' + t).style.display = t === name ? 'block' : 'none';
    document.querySelectorAll('.tab')[i].classList.toggle('active', t === name);
  });
  if (name === 'sim' && simData) requestAnimationFrame(() => drawActivityChart(simData.dayStats));
}

// ── Init ─────────────────────────────────────────────────────────
function init() {
  resetDefaults();
  updateRevPreview();
}
