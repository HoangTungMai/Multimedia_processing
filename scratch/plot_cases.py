"""Vẽ 4 case chỉ với vị trí A, B, BS, PU — không có quỹ đạo."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
RESULTS_DIR = BASE_DIR / "results"

CONFIGS = {
    "Case1_Default": {
        "desc": "PU giữa, BS cạnh (Mặc định)",
        "q_A": [0.0, 0.0], "q_B": [200.0, 200.0],
        "w_BS": [200.0, 0.0], "w_PU": [100.0, 100.0],
    },

    "Case3_BS_Far": {
        "desc": "BS ở xa, PU gần BS",
        "q_A": [0.0, 0.0], "q_B": [200.0, 200.0],
        "w_BS": [300.0, 50.0], "w_PU": [250.0, 80.0],
    },
    "Case4_Opposite": {
        "desc": "PU và BS đối diện nhau",
        "q_A": [0.0, 0.0], "q_B": [200.0, 200.0],
        "w_BS": [50.0, 200.0], "w_PU": [200.0, 50.0],
    },
    "Case5_PU_Near_Start": {
        "desc": "PU gần điểm xuất phát A",
        "q_A": [0.0, 0.0], "q_B": [200.0, 200.0],
        "w_BS": [200.0, 0.0], "w_PU": [30.0, 30.0],
    },
}

fig, axes = plt.subplots(2, 2, figsize=(12, 10))
axes = axes.flatten()

for idx, (case_name, cfg) in enumerate(CONFIGS.items()):
    ax = axes[idx]
    q_A = np.array(cfg["q_A"])
    q_B = np.array(cfg["q_B"])
    w_BS = np.array(cfg["w_BS"])
    w_PU = np.array(cfg["w_PU"])

    # Đường thẳng A→B (đường bay trực tiếp)
    ax.plot([q_A[0], q_B[0]], [q_A[1], q_B[1]], 'k--', alpha=0.25, lw=1.5,
            label='Direct path A→B')

    # Vùng ảnh hưởng PU (interference zone)
    circle = plt.Circle(w_PU, 30, color='red', fill=True, alpha=0.08,
                        lw=1.5, linestyle='--', edgecolor='red')
    ax.add_patch(circle)
    ax.text(w_PU[0], w_PU[1] - 40, 'Interference\nzone',
            ha='center', fontsize=8, color='red', alpha=0.7)

    # Các điểm chính
    ax.plot(*q_A, 'gs', ms=14, zorder=5)
    ax.annotate('A (Start)', q_A, textcoords='offset points',
                xytext=(10, -15), fontsize=10, fontweight='bold', color='green')

    ax.plot(*q_B, 'g^', ms=14, zorder=5)
    ax.annotate('B (End)', q_B, textcoords='offset points',
                xytext=(-50, 10), fontsize=10, fontweight='bold', color='green')

    ax.plot(*w_BS, 'kD', ms=12, zorder=5)
    ax.annotate(f'BS ({w_BS[0]:.0f},{w_BS[1]:.0f})', w_BS,
                textcoords='offset points', xytext=(10, -15),
                fontsize=10, fontweight='bold', color='black')

    ax.plot(*w_PU, 'r^', ms=14, zorder=5)
    ax.annotate(f'PU ({w_PU[0]:.0f},{w_PU[1]:.0f})', w_PU,
                textcoords='offset points', xytext=(10, 8),
                fontsize=11, fontweight='bold', color='red')

    # Axis setup
    all_x = [q_A[0], q_B[0], w_BS[0], w_PU[0]]
    all_y = [q_A[1], q_B[1], w_BS[1], w_PU[1]]
    margin = 50
    ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
    ax.set_ylim(min(all_y) - margin, max(all_y) + margin)
    ax.set_title(f"{case_name}\n{cfg['desc']}", fontsize=11, fontweight='bold')
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')
    ax.legend(fontsize=8, loc='best')

fig.suptitle("4 Cấu Hình PU/BS — Trước Khi Tối Ưu Quỹ Đạo",
             fontsize=15, fontweight='bold')
fig.tight_layout(rect=[0, 0, 1, 0.95])
out_path = str(RESULTS_DIR / "cases_no_trajectory.png")
fig.savefig(out_path, dpi=150)
print(f"Saved: {out_path}")
