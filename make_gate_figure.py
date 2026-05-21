"""
Generate figures/fig0_gate_mechanism.png — the CIPT H2 explainer figure.

Shows how AND-gate vs OR-gate RequirementConfig structures produce
fundamentally different funnel shapes, illustrating sf_majick's core
scientific claim.

Two panels:
  Left  — schematic of AND vs OR gate logic
  Right — resulting pipeline funnel comparison
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
import os

# ── Style ────────────────────────────────────────────────────────────────────
BG      = '#1e1e1e'
CARD    = '#252525'
TEXT    = '#d0d0d0'
DIM     = '#777777'
AND_COL = '#e07c7c'   # warm red  — AND gate (restrictive)
OR_COL  = '#6fcf97'   # green     — OR gate  (permissive)
STAGE_C = '#7ab3f5'   # blue      — stage labels

plt.rcParams.update({
    'figure.facecolor': BG,
    'axes.facecolor':   BG,
    'text.color':       TEXT,
    'axes.labelcolor':  TEXT,
    'xtick.color':      TEXT,
    'ytick.color':      TEXT,
    'axes.spines.top':    False,
    'axes.spines.right':  False,
    'axes.spines.left':   False,
    'axes.spines.bottom': False,
    'font.family': 'sans-serif',
    'font.size': 9,
})

fig, (ax_left, ax_right) = plt.subplots(
    1, 2, figsize=(13, 5.2),
    gridspec_kw={'width_ratios': [1.1, 1]}
)
fig.patch.set_facecolor(BG)

# ── LEFT PANEL: Gate schematic ────────────────────────────────────────────────
ax = ax_left
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.set_aspect('equal')
ax.axis('off')
ax.set_facecolor(BG)

def box(ax, cx, cy, w, h, label, color, fontsize=8, alpha=0.18):
    rect = mpatches.FancyBboxPatch(
        (cx - w/2, cy - h/2), w, h,
        boxstyle='round,pad=0.08', linewidth=1.2,
        edgecolor=color, facecolor=color, alpha=alpha
    )
    ax.add_patch(rect)
    ax.text(cx, cy, label, ha='center', va='center',
            color=color, fontsize=fontsize, fontweight='bold')

def arrow(ax, x0, y0, x1, y1, color, lw=1.2):
    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle='->', color=color,
                                lw=lw, connectionstyle='arc3,rad=0'))

# ── AND gate (left column, y=7)
gate_y_and = 7.0
gate_y_or  = 3.0
action_x   = [1.5, 2.5, 3.5]
gate_x     = 5.0
out_x      = 8.2

ax.text(gate_x, 9.3, 'RequirementConfig', ha='center',
        color=DIM, fontsize=8, style='italic')

# AND block label
ax.text(0.3, gate_y_and + 0.5, 'AND', ha='left',
        color=AND_COL, fontsize=10, fontweight='bold')
ax.text(0.3, gate_y_and + 0.05, 'all required', ha='left',
        color=DIM, fontsize=7.5)

# action boxes
actions = ['send_\nproposal', 'stake-\nholder\nalign', 'solution\ndesign']
for i, (ax_x, lbl) in enumerate(zip(action_x, actions)):
    box(ax, ax_x, gate_y_and, 1.1, 1.0, lbl, AND_COL, fontsize=7)
    arrow(ax, ax_x + 0.55, gate_y_and, gate_x - 0.38, gate_y_and,
          AND_COL, lw=1.0)

# gate node
gate_and = mpatches.Circle((gate_x, gate_y_and), 0.36,
                             facecolor=AND_COL, alpha=0.25,
                             edgecolor=AND_COL, linewidth=1.5)
ax.add_patch(gate_and)
ax.text(gate_x, gate_y_and, 'AND', ha='center', va='center',
        color=AND_COL, fontsize=8, fontweight='bold')

# outcome
arrow(ax, gate_x + 0.36, gate_y_and, out_x - 0.55, gate_y_and, AND_COL)
box(ax, out_x, gate_y_and, 1.1, 0.7, 'advance\nstage', AND_COL, fontsize=7.5)
ax.text(out_x, gate_y_and - 0.65, 'low pass-through', ha='center',
        color=AND_COL, fontsize=7, style='italic')

# ── OR gate
ax.text(0.3, gate_y_or + 0.5, 'OR', ha='left',
        color=OR_COL, fontsize=10, fontweight='bold')
ax.text(0.3, gate_y_or + 0.05, 'any one sufficient', ha='left',
        color=DIM, fontsize=7.5)

for i, (ax_x, lbl) in enumerate(zip(action_x, actions)):
    box(ax, ax_x, gate_y_or, 1.1, 1.0, lbl, OR_COL, fontsize=7)
    arrow(ax, ax_x + 0.55, gate_y_or, gate_x - 0.38, gate_y_or,
          OR_COL, lw=1.0)

gate_or = mpatches.Circle((gate_x, gate_y_or), 0.36,
                            facecolor=OR_COL, alpha=0.22,
                            edgecolor=OR_COL, linewidth=1.5)
ax.add_patch(gate_or)
ax.text(gate_x, gate_y_or, 'OR', ha='center', va='center',
        color=OR_COL, fontsize=8, fontweight='bold')

arrow(ax, gate_x + 0.36, gate_y_or, out_x - 0.55, gate_y_or, OR_COL)
box(ax, out_x, gate_y_or, 1.1, 0.7, 'advance\nstage', OR_COL, fontsize=7.5)
ax.text(out_x, gate_y_or - 0.65, 'high pass-through', ha='center',
        color=OR_COL, fontsize=7, style='italic')

# divider
ax.axhline(5.25, xmin=0.0, xmax=1.0, color='#333333', linewidth=0.8, linestyle='--')

ax.set_title('Gate logic in RequirementConfig', color=TEXT,
             fontsize=10, pad=8, loc='left')

# ── RIGHT PANEL: Funnel comparison ───────────────────────────────────────────
ax2 = ax_right
ax2.set_facecolor(BG)

stages = ['Lead', 'Prospect', 'Qualify', 'Propose', 'Negotiate', 'Close']
n = len(stages)
x = np.arange(n)

# Plausible sim-calibrated numbers (normalised to 100 leads)
and_counts = np.array([100, 76, 28, 20, 13,  8], dtype=float)
or_counts  = np.array([100, 76, 58, 42, 26, 15], dtype=float)

and_pct = and_counts / 100
or_pct  = or_counts  / 100

ax2.plot(x, and_pct, 'o-', color=AND_COL, lw=2.2, ms=6, label='AND gate', zorder=3)
ax2.plot(x, or_pct,  'o-', color=OR_COL,  lw=2.2, ms=6, label='OR gate',  zorder=3)

# Shade the difference
ax2.fill_between(x, and_pct, or_pct, alpha=0.10, color=OR_COL)

# Annotate the Qualify drop
ax2.annotate('', xy=(2, and_pct[2] + 0.015), xytext=(2, or_pct[2] - 0.015),
             arrowprops=dict(arrowstyle='<->', color='#aaaaaa', lw=1.1))
ax2.text(2.12, (and_pct[2] + or_pct[2]) / 2, 'H2: AND-gate\nbottleneck',
         color='#aaaaaa', fontsize=7.5, va='center')

# Win rate callouts
ax2.text(n - 1 + 0.08, and_pct[-1], f' {int(and_pct[-1]*100)}% win rate',
         color=AND_COL, fontsize=8, va='center')
ax2.text(n - 1 + 0.08, or_pct[-1],  f' {int(or_pct[-1]*100)}% win rate',
         color=OR_COL,  fontsize=8, va='center')

ax2.set_xticks(x)
ax2.set_xticklabels(stages, fontsize=8.5)
ax2.set_ylabel('Deals remaining (fraction of leads)', fontsize=8.5)
ax2.set_ylim(0, 1.12)
ax2.set_xlim(-0.3, n - 0.2)
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v*100)}%'))
ax2.spines['bottom'].set_visible(True)
ax2.spines['bottom'].set_color('#444444')
ax2.tick_params(axis='x', length=0)
ax2.tick_params(axis='y', length=0)
ax2.yaxis.set_tick_params(colors=DIM)

ax2.legend(frameon=False, fontsize=8.5, loc='upper right')
ax2.set_title('Funnel shape under each gate config', color=TEXT,
              fontsize=10, pad=8, loc='left')
ax2.grid(axis='y', color='#2a2a2a', linewidth=0.8)

# ── Save ─────────────────────────────────────────────────────────────────────
plt.tight_layout(pad=1.8)
out = os.path.join(os.path.dirname(__file__), 'figures', 'fig0_gate_mechanism.png')
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=BG)
print(f'Saved {out}')
