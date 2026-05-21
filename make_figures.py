"""
make_figures.py -- generate whitepaper plots from simulation CSVs.
Run from sf_majick/ directory:  python make_figures.py
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from pathlib import Path

Path('figures').mkdir(exist_ok=True)

df        = pd.read_csv('data/whitepaper_results.csv')
funnel_df = pd.read_csv('data/whitepaper_funnel.csv',      index_col='condition')
trans_df  = pd.read_csv('data/whitepaper_transitions.csv', index_col='condition')

CONDITION_ORDER  = ['tight_and', 'default_gates', 'loose_or']
CONDITION_LABELS = {'tight_and': 'Tight AND', 'default_gates': 'Default', 'loose_or': 'Loose OR'}
COLORS           = {'tight_and': '#c0392b',    'default_gates': '#7f8c8d',  'loose_or': '#27ae60'}
label_order = [CONDITION_LABELS[c] for c in CONDITION_ORDER]
color_list  = [COLORS[c] for c in CONDITION_ORDER]
SAVEFIG_KW  = dict(dpi=150, bbox_inches='tight')

funnel_df = funnel_df.loc[CONDITION_ORDER]
trans_df  = trans_df.loc[CONDITION_ORDER]

def hide_spines(ax):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


# ── Figure 1: Win Rate Paradox ────────────────────────────────────────────────
print('Generating fig1...')
means = df.groupby('condition')[['won_rate', 'revenue']].mean()
sems  = df.groupby('condition')[['won_rate', 'revenue']].sem()

fig, (ax_wr, ax_rev) = plt.subplots(1, 2, figsize=(9, 4))

# Left: win rate
vals_wr = [float(means.loc[c, 'won_rate']) for c in CONDITION_ORDER]
errs_wr = [float(sems.loc[c,  'won_rate']) for c in CONDITION_ORDER]
bars = ax_wr.bar(label_order, vals_wr, color=color_list, width=0.5,
                 yerr=errs_wr, capsize=4, error_kw=dict(lw=1.2, color='#444444'))
ax_wr.set_title('Win Rate', fontsize=12, fontweight='bold', pad=8)
ax_wr.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))
ax_wr.set_ylim(0, 0.85)
ax_wr.tick_params(axis='x', labelsize=10)
hide_spines(ax_wr)
for bar, val in zip(bars, vals_wr):
    ax_wr.text(bar.get_x() + bar.get_width() / 2,
               bar.get_height() + 0.03,
               f'{val:.1%}', ha='center', va='bottom', fontsize=9, fontweight='bold')

# Right: revenue
vals_rev = [float(means.loc[c, 'revenue']) for c in CONDITION_ORDER]
errs_rev = [float(sems.loc[c,  'revenue']) for c in CONDITION_ORDER]
bars = ax_rev.bar(label_order, vals_rev, color=color_list, width=0.5,
                  yerr=errs_rev, capsize=4, error_kw=dict(lw=1.2, color='#444444'))
ax_rev.set_title('Revenue (60-day sim)', fontsize=12, fontweight='bold', pad=8)
ax_rev.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'${v/1000:.0f}k'))
ax_rev.set_ylim(0, max(vals_rev) * 1.3)
ax_rev.tick_params(axis='x', labelsize=10)
hide_spines(ax_rev)
for bar, val in zip(bars, vals_rev):
    ax_rev.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(vals_rev) * 0.03,
                f'${val/1000:.0f}k', ha='center', va='bottom', fontsize=9, fontweight='bold')

fig.suptitle('Win Rate vs. Revenue by Gate Architecture',
             fontsize=13, fontweight='bold', y=1.02)
fig.text(0.5, -0.04,
         'Tight AND gates inflate win rate while suppressing revenue.\n'
         'Loose OR gates produce 86% more revenue at a lower reported win rate.',
         ha='center', fontsize=9, style='italic', color='#444444')
plt.tight_layout()
plt.savefig('figures/fig1_winrate_paradox.png', **SAVEFIG_KW)
plt.close()
print('  fig1 saved')


# ── Figure 2: Revenue Distribution ───────────────────────────────────────────
print('Generating fig2...')
fig, ax = plt.subplots(figsize=(7, 4))
data_rev = [df.loc[df['condition'] == c, 'revenue'].values for c in CONDITION_ORDER]
bp = ax.boxplot(data_rev, labels=label_order, patch_artist=True,
                medianprops=dict(color='white', linewidth=2),
                whiskerprops=dict(linewidth=1.2), capprops=dict(linewidth=1.2),
                flierprops=dict(marker='o', markersize=4, alpha=0.5))
for patch, color in zip(bp['boxes'], color_list):
    patch.set_facecolor(color)
    patch.set_alpha(0.8)
rng = np.random.default_rng(42)
for i, (cond, color) in enumerate(zip(CONDITION_ORDER, color_list), start=1):
    y = df.loc[df['condition'] == cond, 'revenue'].values
    x = rng.uniform(i - 0.15, i + 0.15, len(y))
    ax.scatter(x, y, color=color, alpha=0.4, s=20, zorder=3)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'${v/1000:.0f}k'))
ax.set_ylabel('Revenue per run', fontsize=10)
ax.set_title('Revenue Distribution by Gate Architecture (20 runs each)',
             fontsize=12, fontweight='bold', pad=8)
hide_spines(ax)
plt.tight_layout()
plt.savefig('figures/fig2_revenue_distribution.png', **SAVEFIG_KW)
plt.close()
print('  fig2 saved')


# ── Figure 3: Funnel Shape ────────────────────────────────────────────────────
print('Generating fig3...')
STAGE_COLS   = ['Prospecting', 'Qualification', 'Proposal',
                'Negotiation', 'Closed_Won', 'Closed_Lost']
STAGE_LABELS = ['Prospecting', 'Qualification', 'Proposal',
                'Negotiation', 'Closed Won',  'Closed Lost']

x     = np.arange(len(STAGE_COLS))
width = 0.25
fig, ax = plt.subplots(figsize=(10, 4.5))
for i, (cond, color) in enumerate(zip(CONDITION_ORDER, color_list)):
    vals = funnel_df.loc[cond, STAGE_COLS].values.astype(float)
    ax.bar(x + (i - 1) * width, vals, width,
           label=CONDITION_LABELS[cond], color=color, alpha=0.85)
ax.set_xticks(x)
ax.set_xticklabels(STAGE_LABELS, fontsize=10)
ax.set_ylabel('Mean deals per run', fontsize=10)
ax.set_title('Final Stage Distribution by Gate Architecture',
             fontsize=12, fontweight='bold', pad=8)
ax.legend(fontsize=9, framealpha=0.4)
hide_spines(ax)
tight_qual = float(funnel_df.loc['tight_and', 'Qualification'])
qual_idx   = STAGE_COLS.index('Qualification')
ax.annotate(
    f'Qual backlog\n{tight_qual:.1f} deals\n(2.5x default)',
    xy=(qual_idx - width, tight_qual),
    xytext=(qual_idx - width - 0.7, tight_qual + 0.3),
    arrowprops=dict(arrowstyle='->', color='#c0392b', lw=1.4),
    fontsize=8, color='#c0392b',
)
plt.tight_layout()
plt.savefig('figures/fig3_funnel_shape.png', **SAVEFIG_KW)
plt.close()
print('  fig3 saved')


# ── Figure 4: Stage Transitions ──────────────────────────────────────────────
print('Generating fig4...')
TRANS_COLS = list(trans_df.columns)
x     = np.arange(len(TRANS_COLS))
width = 0.25
fig, ax = plt.subplots(figsize=(8, 4))
for i, (cond, color) in enumerate(zip(CONDITION_ORDER, color_list)):
    ax.bar(x + (i - 1) * width, trans_df.loc[cond].values.astype(float), width,
           label=CONDITION_LABELS[cond], color=color, alpha=0.85)
ax.set_xticks(x)
ax.set_xticklabels(TRANS_COLS, fontsize=9)
ax.set_ylabel('Mean transitions per run', fontsize=10)
ax.set_title('Pipeline Throughput: Stage Transitions per Run',
             fontsize=12, fontweight='bold', pad=8)
ax.legend(fontsize=9, framealpha=0.4)
hide_spines(ax)
ax.set_ylim(0, float(trans_df.values.max()) * 1.25)
plt.tight_layout()
plt.savefig('figures/fig4_transitions.png', **SAVEFIG_KW)
plt.close()
print('  fig4 saved')


# ── Figure 5: Rep Earnings ───────────────────────────────────────────────────
print('Generating fig5...')
fig, ax = plt.subplots(figsize=(7, 4))
data_earn = [df.loc[df['condition'] == c, 'avg_rep_earnings'].values for c in CONDITION_ORDER]
bp = ax.boxplot(data_earn, labels=label_order, patch_artist=True,
                medianprops=dict(color='white', linewidth=2),
                whiskerprops=dict(linewidth=1.2), capprops=dict(linewidth=1.2),
                flierprops=dict(marker='o', markersize=4, alpha=0.5))
for patch, color in zip(bp['boxes'], color_list):
    patch.set_facecolor(color)
    patch.set_alpha(0.8)
rng2 = np.random.default_rng(7)
for i, (cond, color) in enumerate(zip(CONDITION_ORDER, color_list), start=1):
    y  = df.loc[df['condition'] == cond, 'avg_rep_earnings'].values
    xj = rng2.uniform(i - 0.15, i + 0.15, len(y))
    ax.scatter(xj, y, color=color, alpha=0.4, s=20, zorder=3)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'${v:,.0f}'))
ax.set_ylabel('Avg rep earnings per run', fontsize=10)
ax.set_title('Rep Earnings Distribution by Gate Architecture',
             fontsize=12, fontweight='bold', pad=8)
hide_spines(ax)
plt.tight_layout()
plt.savefig('figures/fig5_rep_earnings.png', **SAVEFIG_KW)
plt.close()
print('  fig5 saved')

print('\nDone. All figures in figures/')
