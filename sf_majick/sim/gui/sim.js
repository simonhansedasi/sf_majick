// sim.js — simulation engine (no DOM access)

const THETA_DEFAULTS = {
  base_prob_prospecting: 0.08, base_prob_qualification: 0.04,
  base_prob_proposal: 0.02,    base_prob_negotiation: 0.01,
  base_prob_close: 0.15,       base_prob_lost: 0.035,
  base_prob_lead_conversion: 0.25,
  inactivity_alpha: 0.010,     stagnation_alpha: 0.008,
  sentiment_beta_opportunity: 0.2, momentum_beta_opportunity: 0.75,
  friction_beta_opportunity: 0.5,
  revenue_base: 1e7,           revenue_exponent: 0.15,
};

const ARCHETYPE_PROPS = {
  Closer:    { aggression:0.85, empathy:0.25, discipline:0.75, burnout:90,  resilience:0.20, distraction:0.08 },
  Nurturer:  { aggression:0.20, empathy:0.90, discipline:0.60, burnout:70,  resilience:0.10, distraction:0.12 },
  Grinder:   { aggression:0.55, empathy:0.50, discipline:0.90, burnout:110, resilience:0.25, distraction:0.04 },
  Scattered: { aggression:0.50, empathy:0.50, discipline:0.20, burnout:60,  resilience:0.08, distraction:0.30 },
};

const ACCOUNT_PERSONALITIES = [
  { name:'Analytical Skeptic',  urgency:0.2, skepticism:0.8, price_sensitivity:0.5 },
  { name:'Urgent Pragmatist',   urgency:0.8, skepticism:0.2, price_sensitivity:0.3 },
  { name:'Price-Sensitive',     urgency:0.5, skepticism:0.5, price_sensitivity:0.9 },
  { name:'Easy-Going Follower', urgency:0.3, skepticism:0.2, price_sensitivity:0.2 },
];

const SENTIMENT_EFFECTS = {
  send_email:0.05, make_call:0.08, hold_meeting:0.15, follow_up:0.10,
  send_proposal:0.12, research_account:0.02, internal_prep:0.01,
  solution_design:0.04, stakeholder_alignment:0.08,
};

const ACTION_COSTS = {
  send_email:15, make_call:15, research_account:25, internal_prep:25,
  solution_design:35, hold_meeting:40, follow_up:30,
  stakeholder_alignment:40, send_proposal:50,
};

const STAGE_ADV_REQS = {
  Prospecting:   { send_email:2, make_call:1 },
  Qualification: { send_email:4, make_call:3, hold_meeting:1 },
  Proposal:      { send_email:6, make_call:4, hold_meeting:2, follow_up:1 },
  Negotiation:   { send_email:8, make_call:6, hold_meeting:2, follow_up:2, send_proposal:1 },
};

const STAGE_ORDER  = ['Prospecting','Qualification','Proposal','Negotiation'];
const STAGE_COLORS = {
  Prospecting:'#378ADD', Qualification:'#BA7517', Proposal:'#1D9E75',
  Negotiation:'#7F77DD', 'Closed Won':'#0F6E56', 'Closed Lost':'#E24B4A',
};
const ALL_STAGES = ['Prospecting','Qualification','Proposal','Negotiation','Closed Won','Closed Lost'];

// ── Util ────────────────────────────────────────────────────────
function rand(a, b)  { return a + Math.random() * (b - a); }
function randInt(a, b){ return Math.floor(rand(a, b + 1)); }
function clamp(v, lo, hi){ return Math.max(lo, Math.min(hi, v)); }
function lognorm(mu, sigma) {
  const u = Math.random() + Math.random() + Math.random() - 1.5;
  return Math.exp(mu + sigma * u * 1.732);
}
function pickWeighted(weights) {
  const tot = weights.reduce((a,b) => a+b, 0) || 1;
  let r = Math.random() * tot, cum = 0;
  for (let i = 0; i < weights.length; i++) { cum += weights[i]; if (r <= cum) return i; }
  return weights.length - 1;
}

// ── Simulation ───────────────────────────────────────────────────
function runSimulation(cfg) {
  const theta = {
    ...THETA_DEFAULTS,
    base_prob_close:             cfg.base_prob_close,
    base_prob_lost:              cfg.base_prob_lost,
    base_prob_prospecting:       cfg.base_prob_prospecting,
    base_prob_qualification:     cfg.base_prob_qualification,
    base_prob_proposal:          cfg.base_prob_proposal,
    base_prob_negotiation:       cfg.base_prob_negotiation,
    base_prob_lead_conversion:   cfg.base_prob_lead_conversion,
    inactivity_alpha:            cfg.inactivity_alpha,
    stagnation_alpha:            cfg.stagnation_alpha,
    sentiment_beta_opportunity:  cfg.sentiment_beta_opportunity,
    momentum_beta_opportunity:   cfg.momentum_beta_opportunity,
    friction_beta_opportunity:   cfg.friction_beta_opportunity,
  };

  // Build reps
  const archNames   = ['Closer','Nurturer','Grinder','Scattered'];
  const archWeights = [cfg.closer, cfg.nurturer, cfg.grinder, cfg.scattered];
  const reps = Array.from({ length: cfg.n_reps }, (_, i) => {
    const arch = archNames[pickWeighted(archWeights)];
    return {
      id: `rep_${i}`, arch,
      earnings: 0, stress: 0, motivation: 1.0,
      wins: 0, losses: 0, comp_rate: cfg.comp_rate,
      ...ARCHETYPE_PROPS[arch],
    };
  });

  // Build opps
  const perWeights = [cfg.p_skeptic, cfg.p_urgent, cfg.p_price, cfg.p_easy];
  const allActions = Object.keys(SENTIMENT_EFFECTS);

  function mkOpp(i, repId) {
    const rev  = lognorm(cfg.rev_mu, cfg.rev_sigma);
    const diff = clamp(Math.random() * cfg.difficulty_mean * 2, 0.005, cfg.difficulty_mean * 3);
    const pers = ACCOUNT_PERSONALITIES[pickWeighted(perWeights)];
    return {
      id: `opp_${i}`, name: `Account_${i}`, rep_id: repId,
      stage: 'Prospecting', revenue: rev, difficulty: diff,
      sentiment: (Math.random() - 0.5) * 0.4,
      sentiment_history: [], days_in_stage: 0, days_since_touch: 0,
      touched_today: false, is_closed: false,
      micro: Object.fromEntries(allActions.map(k => [k, 0])),
      personality: pers.name, urgency: pers.urgency,
      skepticism: pers.skepticism, price_sensitivity: pers.price_sensitivity,
      close_day: null, outcome: null,
    };
  }

  const opps = Array.from({ length: cfg.n_accounts }, (_, i) =>
    mkOpp(i, reps[i % reps.length].id)
  );

  function meetsReqs(opp, stage) {
    return Object.entries(STAGE_ADV_REQS[stage] || {}).every(([a,n]) => (opp.micro[a]||0) >= n);
  }

  const dayStats = [];

  for (let day = 0; day < cfg.days; day++) {
    const isWeekend = (day % 7 === 5 || day % 7 === 6);
    let dayActs = 0, dayWon = 0, dayLost = 0, dayAdv = 0;

    for (const rep of reps) {
      // Stress decays every day including weekends
      rep.stress = Math.max(0, rep.stress - rep.resilience * (isWeekend ? 8 : 4));

      if (isWeekend) {
        // Deals still age over the weekend — inactivity and stagnation accumulate
        const myOpps = opps.filter(o => o.rep_id === rep.id && !o.is_closed);
        for (const opp of myOpps) { opp.days_since_touch++; opp.days_in_stage++; }
        continue;
      }

      const burning = rep.stress >= rep.burnout;
      let attn = burning ? 160 : 360;
      attn = Math.floor(attn * (0.60 + 0.40 * rep.motivation));
      if (Math.random() < rep.distraction) attn -= randInt(30, 80);

      const myOpps = opps.filter(o => o.rep_id === rep.id && !o.is_closed);
      if (!myOpps.length) continue;

      const nWork  = Math.min(myOpps.length, Math.max(1, Math.floor(attn / 110)));
      myOpps.sort((a,b) => STAGE_ORDER.indexOf(b.stage) - STAGE_ORDER.indexOf(a.stage));
      const worked = myOpps.slice(0, nWork);

      for (const opp of worked) {
        opp.touched_today = true;
        opp.days_since_touch = 0;

        let oppAttn = Math.floor(attn / worked.length);
        const nActs = randInt(2, 5);

        for (let ai = 0; ai < nActs && oppAttn > 15; ai++) {
          const actionWeights = allActions.map(a => {
            let w = 1.0;
            if (['make_call','hold_meeting','send_proposal','stakeholder_alignment'].includes(a)) w *= 1 + rep.aggression;
            if (['send_email','follow_up','internal_prep'].includes(a))                          w *= 1 + rep.empathy;
            if (['research_account','internal_prep','solution_design'].includes(a))              w *= 1 + rep.discipline;
            if (rep.discipline < 0.35 && ['send_email','make_call'].includes(a))                w *= 1.5;
            return w;
          });
          const action = allActions[pickWeighted(actionWeights)];
          const cost   = ACTION_COSTS[action] || 20;
          if (oppAttn < cost) continue;

          // Closer skips prep actions
          if (['internal_prep','research_account','solution_design'].includes(action)
              && rep.aggression > 0.70 && Math.random() < (rep.aggression - 0.70)) continue;

          oppAttn -= cost;
          opp.micro[action]++;
          dayActs++;

          let delta = (SENTIMENT_EFFECTS[action] || 0.05) * (0.4 + Math.random() * 0.8);
          delta *= 1 + opp.urgency * 0.25 - opp.skepticism * 0.15 - opp.price_sensitivity * 0.05;
          if (rep.arch === 'Closer'   && ['hold_meeting','send_proposal'].includes(action)) delta *= 1.3;
          if (rep.arch === 'Nurturer' && ['follow_up','send_email','hold_meeting'].includes(action)) delta *= 1.2;
          opp.sentiment = clamp(opp.sentiment + delta, -5, 5);
          opp.sentiment_history.push(delta);
        }

        // Nurturer bonus touch
        if (rep.empathy > 0.75 && Math.random() < (rep.empathy - 0.75) && oppAttn > 30) {
          opp.micro['follow_up']++;
          opp.sentiment = clamp(opp.sentiment + 0.08, -5, 5);
        }

        const momentum = opp.sentiment_history.slice(-5).reduce((a,b) => a+b, 0) / 5;
        const friction = Math.max(0, -momentum);

        // Stage advancement
        const idx = STAGE_ORDER.indexOf(opp.stage);
        if (idx >= 0 && idx < STAGE_ORDER.length - 1) {
          const next = STAGE_ORDER[idx + 1];
          if (meetsReqs(opp, next)) {
            const base = [theta.base_prob_prospecting, theta.base_prob_qualification,
                          theta.base_prob_proposal, theta.base_prob_negotiation][idx];
            const diffScaled = opp.difficulty * Math.pow(opp.revenue / theta.revenue_base, theta.revenue_exponent);
            const p = clamp(
              base
              + momentum  * theta.momentum_beta_opportunity * 0.35
              - friction  * theta.friction_beta_opportunity * 0.35
              + opp.sentiment * theta.sentiment_beta_opportunity * 0.5
              - diffScaled,
              0.005, 0.50
            );
            if (Math.random() < p) { opp.stage = next; opp.days_in_stage = 0; dayAdv++; }
          }
        }

        // Close
        if (opp.stage === 'Negotiation' && meetsReqs(opp, 'Negotiation')) {
          const diffScaled = opp.difficulty * Math.pow(opp.revenue / theta.revenue_base, 0.05);
          const pClose = clamp(
            theta.base_prob_close
            + momentum * theta.momentum_beta_opportunity * 0.40
            - friction * theta.friction_beta_opportunity * 0.30
            + opp.sentiment * theta.sentiment_beta_opportunity * 0.30
            - diffScaled,
            0.005, 0.70
          );
          if (Math.random() < pClose) {
            opp.stage = 'Closed Won'; opp.is_closed = true; opp.close_day = day; opp.outcome = 'won';
            const commission = opp.revenue * cfg.commission_rate * rep.comp_rate * (rep.arch === 'Closer' ? 1.15 : 1.0);
            rep.earnings += commission; rep.wins++;
            rep.motivation = Math.min(1.0, rep.motivation + 0.18);
            rep.stress = Math.max(0, rep.stress - 4);
            dayWon++;
            continue;
          }
        }

        // Lost
        const pLost = clamp(
          theta.base_prob_lost
          + theta.inactivity_alpha * Math.log1p(opp.days_since_touch)
          + theta.stagnation_alpha * Math.log1p(opp.days_in_stage),
          0, 0.35
        );
        if (Math.random() < pLost) {
          opp.stage = 'Closed Lost'; opp.is_closed = true; opp.close_day = day; opp.outcome = 'lost';
          rep.losses++;
          rep.motivation = Math.max(0.1, rep.motivation - 0.05);
          rep.stress += 2.5;
          dayLost++;
        }
      }

      for (const opp of myOpps) {
        if (!opp.touched_today && !opp.is_closed) { opp.days_since_touch++; opp.days_in_stage++; }
        opp.touched_today = false;
      }
      rep.stress = Math.min(rep.stress + 0.4 * dayActs / Math.max(worked.length, 1), 200);
    }

    dayStats.push({ day, isWeekend, actions: dayActs, won: dayWon, lost: dayLost, advanced: dayAdv });
  }

  const closed      = opps.filter(o => o.is_closed);
  const won         = closed.filter(o => o.outcome === 'won');
  const lost        = closed.filter(o => o.outcome === 'lost');
  const wonRevenue  = won.reduce((s, o) => s + o.revenue, 0);
  const winRate     = closed.length ? won.length / closed.length : null;
  const avgCycleDays= won.length ? won.reduce((s,o) => s + (o.close_day||0), 0) / won.length : null;
  const avgDealSize = won.length ? wonRevenue / won.length : null;
  const stageCount  = Object.fromEntries(ALL_STAGES.map(s => [s, opps.filter(o => o.stage === s).length]));
  const totalActions= dayStats.reduce((s,d) => s + d.actions, 0);

  return { cfg, reps, opps, won, lost, closed, stageCount, dayStats,
           wonRevenue, winRate, avgCycleDays, avgDealSize, totalActions };
}

// ── Calibrator (mirrors OrgCalibrator.calibrate()) ───────────────
function calibrateFromSim(data) {
  const { opps, won, lost, closed, winRate, avgCycleDays, reps, cfg } = data;

  const base_prob_close = winRate != null ? +clamp(winRate, 0.01, 0.60).toFixed(4) : null;

  const lostRate = opps.length ? lost.length / opps.length : null;
  const cycle    = avgCycleDays || 60;
  const base_prob_lost = lostRate != null ? +clamp(lostRate / Math.max(cycle, 1), 0.001, 0.10).toFixed(5) : null;

  const inactivity_alpha = +clamp(0.010 * (45 / Math.max(cycle, 10)), 0.002, 0.025).toFixed(5);
  const stagnation_alpha = +clamp(0.008 * (45 / Math.max(cycle, 10)), 0.001, 0.020).toFixed(5);

  function advRate(stage) {
    const idx = STAGE_ORDER.indexOf(stage);
    const atOrPast = opps.filter(o => {
      const oi = STAGE_ORDER.indexOf(o.stage);
      return oi >= idx || o.outcome === 'won' || o.outcome === 'lost';
    }).length;
    const past = opps.filter(o => {
      const oi = STAGE_ORDER.indexOf(o.stage);
      return oi > idx || o.outcome === 'won' || o.outcome === 'lost';
    }).length;
    return atOrPast > 0 ? past / atOrPast : null;
  }

  const avgDays = { Prospecting:25, Qualification:20, Proposal:15, Negotiation:12 };
  function toDaily(stage, rate) {
    return rate != null ? +clamp(rate / avgDays[stage], 0.001, 0.30).toFixed(4) : null;
  }

  const archCounts = {};
  for (const r of reps) archCounts[r.arch] = (archCounts[r.arch]||0) + 1;
  const archetype_weights = {};
  for (const [k,v] of Object.entries(archCounts)) archetype_weights[k] = +(v/reps.length).toFixed(2);

  const prospAdv = advRate('Prospecting');
  const qualAdv  = advRate('Qualification');
  const propAdv  = advRate('Proposal');

  return {
    label: 'fitted_from_sim',
    n_reps: reps.length,
    archetype_weights,
    n_seed_accounts: cfg.n_accounts,
    n_seed_leads:    cfg.n_leads,
    days: cfg.days,
    n_runs: 100,
    base_prob_close,
    base_prob_lost,
    base_prob_prospecting:   toDaily('Prospecting', prospAdv),
    base_prob_qualification: toDaily('Qualification', qualAdv),
    base_prob_proposal:      toDaily('Proposal', propAdv),
    inactivity_alpha,
    stagnation_alpha,
    apply_decay: true,
    notes: `Fitted from ${cfg.days}-day sim. ${won.length} won, ${lost.length} lost of ${opps.length} opps.`,
    _observed: {
      win_rate:       winRate != null ? +(winRate*100).toFixed(1) : null,
      avg_cycle_days: avgCycleDays != null ? +avgCycleDays.toFixed(1) : null,
      avg_deal_size:  data.avgDealSize != null ? +data.avgDealSize.toFixed(0) : null,
      total_actions:  data.totalActions,
      adv_rates: { Prospecting: prospAdv, Qualification: qualAdv, Proposal: propAdv },
    },
  };
}
