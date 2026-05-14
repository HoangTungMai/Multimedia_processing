"""Vẽ sơ đồ tổng quan hệ thống UAV CR-NOMA Video Transmission."""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

fig, ax = plt.subplots(1, 1, figsize=(16, 10))
ax.set_xlim(0, 16)
ax.set_ylim(0, 10)
ax.axis('off')

# Colors
C_BLUE = '#1565C0'
C_LBLUE = '#BBDEFB'
C_ORANGE = '#E65100'
C_LORANGE = '#FFE0B2'
C_GREEN = '#1B5E20'
C_LGREEN = '#C8E6C9'
C_PURPLE = '#6A1B9A'
C_LPURPLE = '#E1BEE7'
C_RED = '#C62828'
C_LRED = '#FFCDD2'
C_DARK = '#263238'
C_GRAY = '#ECEFF1'
C_GOLD = '#FF8F00'

def draw_box(x, y, w, h, color, edge_color, text, fontsize=9, bold=False):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                         facecolor=color, edgecolor=edge_color, linewidth=2)
    ax.add_patch(box)
    weight = 'bold' if bold else 'normal'
    ax.text(x + w/2, y + h/2, text, ha='center', va='center',
            fontsize=fontsize, fontweight=weight, color=C_DARK,
            linespacing=1.4)

def draw_arrow(x1, y1, x2, y2, color=C_DARK, style='->', lw=2):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw))

def draw_label(x, y, text, fontsize=8, color='#546E7A', ha='center'):
    ax.text(x, y, text, ha=ha, va='center', fontsize=fontsize, color=color,
            fontstyle='italic')

# =====================================================================
# TITLE
# =====================================================================
ax.text(8, 9.6, 'UAV CR-NOMA Video Transmission — System Overview',
        ha='center', va='center', fontsize=16, fontweight='bold', color=C_DARK)
ax.plot([1, 15], [9.35, 9.35], color=C_BLUE, lw=2)

# =====================================================================
# LAYER 1: VIDEO SOURCE (top-left)
# =====================================================================
draw_box(0.3, 7.8, 2.2, 1.2, C_LGREEN, C_GREEN,
         '📹 Video Source\n─────────\nForeman CIF\n352×288 YUV', 9, True)

# =====================================================================
# LAYER 2: OPTIMIZER (top-center)
# =====================================================================
draw_box(3.5, 7.8, 3.5, 1.2, C_LBLUE, C_BLUE,
         '⚙️ BCD + SCA Optimizer\n──────────────\nTối ưu: P(t), q(t)\n→ R(t) Channel Rate', 9, True)

# Arrow Video → Optimizer
draw_arrow(2.5, 8.4, 3.5, 8.4, C_GREEN)
draw_label(3.0, 8.7, 'MAD', 8, C_GREEN)

# =====================================================================
# LAYER 3: QP MAPPING (top-right)
# =====================================================================
draw_box(8.0, 7.8, 2.8, 1.2, C_LORANGE, C_ORANGE,
         '📐 R-Q Model\n──────────\nR → Qstep → QP\n(Ma, Siwei 2005)', 9, True)

# Arrow Optimizer → QP
draw_arrow(7.0, 8.4, 8.0, 8.4, C_BLUE)
draw_label(7.5, 8.7, 'R(t)', 8, C_BLUE)

# =====================================================================
# LAYER 4: ENCODER (far right)
# =====================================================================
draw_box(11.8, 7.8, 2.5, 1.2, C_LGREEN, C_GREEN,
         '🎬 H.264 Encoder\n──────────\nFFmpeg libx264\nAdaptive QP / SVC', 9, True)

# Arrow QP → Encoder
draw_arrow(10.8, 8.4, 11.8, 8.4, C_ORANGE)
draw_label(11.3, 8.7, 'QP(t)', 8, C_ORANGE)

# Arrow Encoder → Bitstream output
draw_box(14.8, 8.0, 0.9, 0.8, C_GRAY, C_DARK, '💾\n.264', 10, True)
draw_arrow(14.3, 8.4, 14.8, 8.4, C_GREEN)

# =====================================================================
# MIDDLE: CHANNEL MODEL
# =====================================================================
# UAV box
draw_box(0.3, 5.2, 2.8, 1.8, '#E3F2FD', C_BLUE,
         '🛩️ UAV (Transmitter)\n───────────\nVị trí: q(t) = [x,y]\nĐộ cao: H = 100m\nCông suất: P(t) ≤ 0.5W', 8.5)

# BS box
draw_box(6.0, 5.2, 2.8, 1.8, C_LGREEN, C_GREEN,
         '📡 Base Station (BS)\n───────────\nVị trí: w_BS\nNhận tín hiệu UAV\nChannel gain: h(q)', 8.5)

# PU box
draw_box(6.0, 3.0, 2.8, 1.6, C_LRED, C_RED,
         '📻 Primary User (PU)\n───────────\nVị trí: w_PU\nRàng buộc: I ≤ I_th\nBán kính bảo vệ', 8.5)

# Arrow UAV → BS (signal)
draw_arrow(3.1, 6.3, 6.0, 6.3, C_BLUE, '->', 2.5)
draw_label(4.5, 6.6, 'Signal: R(t) = log₂(1 + P·h/σ²)', 9, C_BLUE)

# Arrow UAV → PU (interference)
draw_arrow(2.5, 5.2, 6.0, 3.8, C_RED, '->', 1.5)
draw_label(3.5, 4.2, 'Interference ≤ I_th', 8, C_RED)

# =====================================================================
# MIDDLE-RIGHT: CHANNEL
# =====================================================================
draw_box(10.5, 5.2, 3.0, 1.8, C_LPURPLE, C_PURPLE,
         '📶 CR-NOMA Channel\n───────────\nR(t) = log₂(1+SNR)\nShannon Capacity\nI_PU ≤ I_threshold', 8.5)

# Arrows
draw_arrow(8.8, 6.1, 10.5, 6.1, C_GREEN, '->')
draw_arrow(8.8, 3.8, 10.5, 5.4, C_RED, '->')

# =====================================================================
# BOTTOM: DECODER + EVALUATION
# =====================================================================
draw_box(0.3, 0.8, 2.5, 1.6, C_LORANGE, C_ORANGE,
         '🔓 H.264 Decoder\n──────────\nParse NAL → CAVLC\n→ Inv.Quant → IDCT\n→ Deblock Filter', 8.5, True)

draw_box(3.5, 0.8, 3.0, 1.6, C_LPURPLE, C_PURPLE,
         '📊 PSNR Evaluation\n──────────\nPSNR = 10·log(255²/MSE)\nFull-Reference metric\nPer-frame comparison', 8.5, True)

# SVC Decode Logic
draw_box(7.2, 0.8, 3.5, 1.6, C_LRED, C_RED,
         'SVC Logic (Decoder)\n──────────\nR ≥ 3.0 → BL+EL (QP≈15)\nR ≥ 2.0 → BL only (QP=35)\nR < 2.0 → Freeze ❌', 8.5)

# Results
draw_box(11.5, 0.8, 4.0, 1.6, '#FFF9C4', C_GOLD,
         '🏆 Kết Quả\n──────────────\nAdaptive QP: 37.5 ~ 39.9 dB\nvs Straight: +3.5 ~ 4.0 dB\nvs SVC: luôn ≥ (trừ R≈3.0)', 8.5, True)

# Arrows bottom flow
draw_arrow(2.8, 1.6, 3.5, 1.6, C_ORANGE)
draw_arrow(6.5, 1.6, 7.2, 1.6, C_PURPLE)
draw_arrow(10.7, 1.6, 11.5, 1.6, C_RED)

# Vertical: Bitstream → Decoder
draw_arrow(15.2, 8.0, 15.2, 3.2, '#78909C', '->', 1.5)
draw_label(15.5, 5.5, 'Transmit', 8, '#78909C', ha='left')
draw_arrow(15.2, 3.2, 2.8, 1.8, '#78909C', '->', 1.5)
draw_label(9.0, 2.8, 'Receive & Decode', 8, '#78909C')

# =====================================================================
# SECTION LABELS
# =====================================================================
ax.text(0.1, 9.15, 'ENCODER', fontsize=11, fontweight='bold', color=C_GREEN,
        bbox=dict(boxstyle='round', facecolor=C_LGREEN, edgecolor=C_GREEN, alpha=0.8))
ax.text(4.5, 4.9, 'CHANNEL', fontsize=11, fontweight='bold', color=C_BLUE,
        bbox=dict(boxstyle='round', facecolor=C_LBLUE, edgecolor=C_BLUE, alpha=0.8))
ax.text(0.1, 2.6, 'DECODER & EVALUATION', fontsize=11, fontweight='bold', color=C_PURPLE,
        bbox=dict(boxstyle='round', facecolor=C_LPURPLE, edgecolor=C_PURPLE, alpha=0.8))

# Feedback loop: Optimizer ←→ Channel
draw_arrow(5.3, 7.8, 5.3, 7.2, C_BLUE, '->', 1.5)
draw_arrow(5.3, 7.2, 11.0, 7.2, C_BLUE, '->', 1.5)
draw_arrow(11.0, 7.2, 11.0, 7.0, C_BLUE, '->', 1.5)
draw_label(8.0, 7.4, 'Cross-layer feedback: R(t) ↔ QP(t)', 8.5, C_BLUE)

plt.tight_layout()
out = 'results/system_overview.png'
fig.savefig(out, dpi=180, bbox_inches='tight', facecolor='white')
print(f'Saved: {out}')
