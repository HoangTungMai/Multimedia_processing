"""
================================================================================
H.264 Quality Evaluator — UAV CR-NOMA Video Transmission
================================================================================
Giải mã bitstream .264 và tính PSNR thực tế (Full-Reference) so với video gốc.
Hỗ trợ đánh giá nhiều cấu hình PU/BS cùng lúc.

Cách chạy:
  python evaluator.py        (cần chạy encoder.py trước)
================================================================================
"""

import cv2
import numpy as np
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

BASE_DIR = Path(__file__).parent
YUV_PATH = BASE_DIR / "foreman_cif.yuv"
BITSTREAM_DIR = BASE_DIR / "results" / "bitstreams"
RESULTS_DIR = BASE_DIR / "results"


class QualityEvaluator:
    def __init__(self, original_yuv, width=352, height=288):
        self.yuv_path = str(original_yuv)
        self.width = width
        self.height = height
        self.frame_size = int(width * height * 1.5)
        print("Loading original YUV frames...")
        self.original_frames = self._load_yuv()
        print(f"  Loaded {len(self.original_frames)} frames")

    def _load_yuv(self):
        frames = []
        with open(self.yuv_path, 'rb') as f:
            while True:
                data = f.read(self.frame_size)
                if not data:
                    break
                yuv = np.frombuffer(data, dtype=np.uint8).reshape(
                    (int(self.height * 1.5), self.width))
                bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
                frames.append(bgr)
        return frames

    def decode_folder(self, folder_path):
        files = sorted([
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.endswith('.264')
        ])
        decoded_frames = []
        for f in files:
            cap = cv2.VideoCapture(f)
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                decoded_frames.append(frame)
            cap.release()
        return decoded_frames

    def calculate_psnr(self, original, decoded):
        mse = np.mean((original.astype(np.float64) - decoded.astype(np.float64)) ** 2)
        if mse == 0:
            return 100
        return 20 * np.log10(255.0 / np.sqrt(mse))

    def evaluate(self, folder_path):
        frames = self.decode_folder(folder_path)
        psnrs = []
        num_frames = min(len(self.original_frames), len(frames))
        for i in range(num_frames):
            psnrs.append(self.calculate_psnr(
                self.original_frames[i], frames[i]))
        return psnrs

    def evaluate_svc(self, svc_dir, rates, r_bl=2.0, r_el=3.0):
        """
        SVC Evaluation (Residual-based):
        - R(t) >= R_BL + R_EL -> nhan duoc ca BL va EL
          → Final = BL_decoded + (EL_decoded - 128)  (cong residual)
        - R(t) >= R_BL -> chi nhan duoc BL
          → Final = BL_decoded
        - R(t) < R_BL -> khong truyen duoc
          → Freeze frame truoc
        """
        bl_dir = os.path.join(svc_dir, "BL")
        el_dir = os.path.join(svc_dir, "EL")
        bl_frames = self.decode_folder(bl_dir)
        el_frames = self.decode_folder(el_dir)  # Đây là residual đã shift +128

        psnrs = []
        frames_per_slot = 10
        prev_frame = None

        for slot_idx, rate in enumerate(rates):
            start = slot_idx * frames_per_slot
            end = start + frames_per_slot

            for i in range(start, min(end, len(self.original_frames))):
                if rate >= r_bl + r_el and i < len(el_frames) and i < len(bl_frames):
                    # Kênh tốt: BL + EL (residual) = video nét
                    combined = np.clip(
                        bl_frames[i].astype(np.int16)
                        + el_frames[i].astype(np.int16) - 128,
                        0, 255
                    ).astype(np.uint8)
                    decoded = combined
                    prev_frame = decoded
                elif rate >= r_bl and i < len(bl_frames):
                    # Kênh trung bình: chỉ BL
                    decoded = bl_frames[i]
                    prev_frame = decoded
                else:
                    # Kênh xấu: freeze
                    if prev_frame is not None:
                        decoded = prev_frame
                    else:
                        decoded = np.zeros_like(self.original_frames[i])

                psnrs.append(self.calculate_psnr(
                    self.original_frames[i], decoded))
        return psnrs

if __name__ == "__main__":
    print("=" * 60)
    print(" UAV CR-NOMA Video Quality Evaluation")
    print(" Multi-Configuration Benchmark")
    print("=" * 60)

    evaluator = QualityEvaluator(YUV_PATH)

    # Tự động phát hiện các case đã encode
    cases = sorted([d.name for d in BITSTREAM_DIR.iterdir()
                    if d.is_dir() and d.name.startswith("Case")])
    if not cases:
        print("[ERROR] No encoded cases found. Run encoder.py first.")
        exit(1)

    METHODS = ["Optimized", "Opt_LogQoE", "Straight", "Circle", "SVC"]
    METHOD_COLORS = {
        "Optimized": "#2196F3",     # Xanh dương — Sigmoid QoE + Adaptive QP
        "Opt_LogQoE": "#FF5722",    # Cam đậm — Log QoE + Adaptive QP
        "Straight": "#FF9800",
        "Circle": "#4CAF50", "SVC": "#9C27B0"
    }
    R_EL_OPTIMAL = 1.0  # Nguong hop ly nhat (Tong = 2.0 + 1.0 = 3.0)


    print(f"\nFound {len(cases)} cases: {cases}")

    all_psnr = {}
    summary = []

    for case_name in cases:
        case_dir = BITSTREAM_DIR / case_name
        print(f"\n  [{case_name}]")
        case_data = {}

        for method in METHODS:
            if method == "SVC":
                # SVC co logic dac biet
                svc_dir = str(case_dir / "SVC")
                rates_path = str(case_dir / "opt_rates.json")
                if not os.path.exists(svc_dir) or not os.path.exists(rates_path):
                    print(f"    [SKIP] {method}: folder or rates missing")
                    continue
                import json
                with open(rates_path, 'r') as f:
                    opt_rates = json.load(f)
                
                psnrs = evaluator.evaluate_svc(svc_dir, opt_rates, r_el=R_EL_OPTIMAL)
                avg = np.mean(psnrs)
                # Tính tỷ lệ dùng EL
                el_count = sum(1 for r in opt_rates if r >= 2.0 + R_EL_OPTIMAL)
                el_pct = el_count / len(opt_rates) * 100
                case_data[method] = {"psnrs": psnrs, "avg": avg, "el_pct": el_pct}
                print(f"    {method:<16}: Avg PSNR = {avg:.2f} dB  (EL dùng {el_pct:.0f}% slots)")

            else:
                method_dir = case_dir / method
                if not method_dir.exists():
                    print(f"    [SKIP] {method}: folder missing")
                    continue
                psnrs = evaluator.evaluate(str(method_dir))
                avg = np.mean(psnrs)
                case_data[method] = {"psnrs": psnrs, "avg": avg}
                print(f"    {method:<12}: Avg PSNR = {avg:.2f} dB")

        if "Optimized" in case_data:
            gain_s = case_data["Optimized"]["avg"] - case_data.get("Straight", {"avg": 0})["avg"]
            gain_c = case_data["Optimized"]["avg"] - case_data.get("Circle", {"avg": 0})["avg"]
            print(f"    Gain vs Straight: {gain_s:+.2f} dB")
            print(f"    Gain vs Circle:   {gain_c:+.2f} dB")

        all_psnr[case_name] = case_data
        summary.append(case_name)

    # ==================================================================
    # Biểu đồ 1: PSNR theo frame cho từng case
    # ==================================================================
    n_cases = len(all_psnr)
    cols = min(3, n_cases)
    rows = (n_cases + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(6*cols, 4*rows))
    if n_cases == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for idx, case_name in enumerate(summary):
        ax = axes[idx]
        data = all_psnr[case_name]
        for method in METHODS:
            if method in data:
                ax.plot(data[method]["psnrs"],
                        color=METHOD_COLORS[method], lw=1.2,
                        label=f'{method} ({data[method]["avg"]:.1f} dB)')
        ax.set_title(f'{case_name}', fontsize=10)
        ax.set_xlabel("Frame"); ax.set_ylabel("PSNR (dB)")
        ax.legend(fontsize=7); ax.grid(True, alpha=0.3)

    for i in range(n_cases, len(axes)):
        axes[i].set_visible(False)

    fig.suptitle("PSNR Comparison — Optimized vs Straight vs Circle",
                 fontsize=13, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path1 = str(RESULTS_DIR / "psnr_all_cases.png")
    fig.savefig(path1, dpi=150)
    print(f"\n  Saved: {path1}")

    # ==================================================================
    # Biểu đồ 2: Bar chart tổng hợp
    # ==================================================================
    fig2, ax2 = plt.subplots(figsize=(12, 5))
    x = np.arange(len(summary))
    width = 0.25

    for i, method in enumerate(METHODS):
        vals = [all_psnr[c].get(method, {"avg": 0})["avg"] for c in summary]
        offset = (i - 1) * width
        bars = ax2.bar(x + offset, vals, width, label=method,
                       color=METHOD_COLORS[method], edgecolor='white')

    # Ghi gain lên bar Optimized
    for i, case_name in enumerate(summary):
        opt_val = all_psnr[case_name].get("Optimized", {"avg": 0})["avg"]
        str_val = all_psnr[case_name].get("Straight", {"avg": 0})["avg"]
        gain = opt_val - str_val
        ax2.annotate(f'+{gain:.1f}', xy=(x[i] - width, opt_val),
                     ha='center', va='bottom', fontsize=8, fontweight='bold',
                     color='#1565C0')

    ax2.set_ylabel('Avg PSNR (dB)', fontsize=11)
    ax2.set_title('PSNR Summary — Optimized vs Straight vs Circle\n'
                  'across different PU/BS configurations',
                  fontsize=12, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(summary, rotation=15, ha='right', fontsize=9)
    ax2.legend(fontsize=10)
    ax2.grid(True, axis='y', alpha=0.3)
    fig2.tight_layout()

    path2 = str(RESULTS_DIR / "psnr_summary_bar.png")
    fig2.savefig(path2, dpi=150)
    print(f"  Saved: {path2}")

    # ==================================================================
    # Bảng tổng kết
    # ==================================================================
    print("\n" + "=" * 75)
    print(f" {'Case':<22} {'Optimized':>10} {'Straight':>10} {'Circle':>10} {'Gain(S)':>10}")
    print("-" * 75)
    for case_name in summary:
        d = all_psnr[case_name]
        o = d.get("Optimized", {"avg": 0})["avg"]
        s = d.get("Straight", {"avg": 0})["avg"]
        c = d.get("Circle", {"avg": 0})["avg"]
        print(f" {case_name:<22} {o:>8.2f}dB {s:>8.2f}dB {c:>8.2f}dB {o-s:>+8.2f}dB")
    print("=" * 75)

    # ==================================================================
    # Biểu đồ 3: Phân tích SVC (Optimal Threshold)
    # ==================================================================
    fig3, (ax3a, ax3b) = plt.subplots(1, 2, figsize=(14, 5))

    # --- 3a: Bar chart so sánh PSNR ---
    x = np.arange(len(summary))
    width = 0.25

    opt_vals = [all_psnr[c].get("Optimized", {"avg": 0})["avg"] for c in summary]
    svc_vals = [all_psnr[c].get("SVC", {"avg": 0})["avg"] for c in summary]
    
    ax3a.bar(x - width/2, opt_vals, width, label='Adaptive QP', color='#2196F3', edgecolor='white')
    ax3a.bar(x + width/2, svc_vals, width, label='SVC (R_EL=1.0)', color='#9C27B0', edgecolor='white')

    ax3a.set_ylabel('Avg PSNR (dB)', fontsize=11)
    ax3a.set_title('Quality Comparison: Adaptive QP vs SVC', fontsize=12, fontweight='bold')
    ax3a.set_xticks(x)
    ax3a.set_xticklabels([c.replace("Case", "C") for c in summary], fontsize=9)
    ax3a.legend(fontsize=9)
    ax3a.grid(True, axis='y', alpha=0.3)

    # --- 3b: Tỷ lệ EL activation ---
    el_pcts = [all_psnr[c].get("SVC", {}).get("el_pct", 0) for c in summary]
    ax3b.bar(x, el_pcts, width*2, color='#9C27B0', alpha=0.7, edgecolor='white')

    ax3b.set_ylabel('EL Activation (%)', fontsize=11)
    ax3b.set_title('SVC Enhancement Layer Usage (R_EL=1.0)', fontsize=12, fontweight='bold')
    ax3b.set_xticks(x)
    ax3b.set_xticklabels([c.replace("Case", "C") for c in summary], fontsize=9)
    ax3b.set_ylim(0, 110)
    ax3b.axhline(y=50, color='gray', linestyle='--', alpha=0.4, label='50% Target')
    ax3b.grid(True, axis='y', alpha=0.3)

    fig3.suptitle('SVC Performance Analysis with Optimal Threshold (Total = 3.0 bps/Hz)',
                  fontsize=13, fontweight='bold')
    fig3.tight_layout(rect=[0, 0, 1, 0.93])
    path3 = str(RESULTS_DIR / "svc_optimal_analysis.png")
    fig3.savefig(path3, dpi=150)
    print(f"  Saved: {path3}")

    # ==================================================================
    # Biểu đồ 4: PSNR per frame — Case1 chi tiết
    # ==================================================================
    ref_case = "Case1_Default"
    if ref_case in all_psnr:
        fig4, ax4 = plt.subplots(figsize=(12, 5))
        d = all_psnr[ref_case]

        if "Optimized" in d:
            ax4.plot(d["Optimized"]["psnrs"], color='#2196F3', lw=1.8,
                     label=f'Adaptive QP ({d["Optimized"]["avg"]:.1f} dB)')
        if "SVC" in d:
            ax4.plot(d["SVC"]["psnrs"], color='#9C27B0', lw=1.5,
                     label=f'SVC R_EL=1.0 ({d["SVC"]["avg"]:.1f} dB)')

        ax4.set_title(f'Frame-by-Frame PSNR: Adaptive QP vs SVC — {ref_case}',
                      fontsize=12, fontweight='bold')
        ax4.set_xlabel('Frame Index', fontsize=11)
        ax4.set_ylabel('PSNR (dB)', fontsize=11)
        ax4.legend(fontsize=9)
        ax4.grid(True, alpha=0.3)
        fig4.tight_layout()

        path4 = str(RESULTS_DIR / "svc_vs_adaptive_detail.png")
        fig4.savefig(path4, dpi=150)
        print(f"  Saved: {path4}")

    # ==================================================================
    # Biểu đồ 5: Tổng hợp lớn — Adaptive QP vs SVC (phong cách uav_scenarios)
    # 5 hàng (cases) × 3 cột (Trajectory, Rate→QP, PSNR per frame)
    # ==================================================================
    import json

    # Load encoder results để lấy trajectory + rates
    encoder_data = {}
    for case_name in summary:
        case_dir = BITSTREAM_DIR / case_name
        rates_path = case_dir / "opt_rates.json"
        if rates_path.exists():
            with open(str(rates_path), 'r') as f:
                encoder_data[case_name] = json.load(f)

    n_cases = len(summary)
    fig5, axes5 = plt.subplots(n_cases, 3, figsize=(18, 4 * n_cases))
    if n_cases == 1:
        axes5 = axes5.reshape(1, -1)

    # Hàm ánh xạ Rate → QP (giống encoder.py)
    def rate_to_qp(r):
        qp = 32 - (r - 2.0) * (22 / 2.0)
        return int(np.clip(qp, 10, 45))

    for row, case_name in enumerate(summary):
        d = all_psnr[case_name]

        # ---- Cột 1: PSNR so sánh tất cả phương pháp ----
        ax = axes5[row, 0]
        for method in METHODS:
            if method in d:
                ax.plot(d[method]["psnrs"], color=METHOD_COLORS[method],
                        lw=1.2 if method not in ["Optimized", "Opt_LogQoE"] else 1.8,
                        alpha=0.6 if method in ["Straight", "Circle"] else 1.0,
                        label=f'{method} ({d[method]["avg"]:.1f}dB)')
        ax.set_ylabel("PSNR (dB)", fontsize=9)
        ax.set_title(f'{case_name} — PSNR per Frame', fontsize=10, fontweight='bold')
        ax.legend(fontsize=7, loc='lower right')
        ax.grid(True, alpha=0.3)
        if row == n_cases - 1:
            ax.set_xlabel("Frame Index")

        # ---- Cột 2: Rate R(t) & QP mapping (Adaptive QP vs SVC) ----
        ax = axes5[row, 1]
        if case_name in encoder_data:
            rates = encoder_data[case_name]
            t_slots = np.arange(1, len(rates) + 1)

            # Vẽ Rate
            ax.plot(t_slots, rates, '-o', color='#2196F3', ms=3, lw=1.5, label='Rate R(t)')

            # Vẽ QP trên trục phụ
            ax2 = ax.twinx()
            qps = [rate_to_qp(r) for r in rates]
            ax2.plot(t_slots, qps, '-s', color='#FF5722', ms=3, lw=1.2, alpha=0.7, label='QP (Adaptive)')
            ax2.axhline(y=35, color='#9C27B0', ls='--', lw=1.5, alpha=0.6, label='QP_BL=35 (SVC)')
            ax2.axhline(y=15, color='#9C27B0', ls=':', lw=1.5, alpha=0.6, label='QP_EL=15 (SVC)')
            ax2.set_ylabel("QP", fontsize=9, color='#FF5722')
            ax2.set_ylim(5, 50)
            ax2.invert_yaxis()  # QP thấp = chất lượng cao → đặt ở trên
            ax2.legend(fontsize=6, loc='lower right')

            # Ngưỡng SVC trên trục Rate
            ax.axhline(y=3.0, color='#9C27B0', ls='--', lw=1, alpha=0.4)
            ax.text(len(rates) + 0.5, 3.0, 'R_BL+R_EL', fontsize=7, color='#9C27B0', va='center')

            ax.set_ylabel("Rate (bps/Hz)", fontsize=9, color='#2196F3')
            ax.legend(fontsize=7, loc='upper left')
        ax.set_title(f'{case_name} — Rate & QP Mapping', fontsize=10, fontweight='bold')
        ax.grid(True, alpha=0.3)
        if row == n_cases - 1:
            ax.set_xlabel("Time Slot")

        # ---- Cột 3: Bar chart PSNR trung bình ----
        ax = axes5[row, 2]
        methods_present = [m for m in METHODS if m in d]
        vals = [d[m]["avg"] for m in methods_present]
        colors = [METHOD_COLORS[m] for m in methods_present]
        bars = ax.barh(methods_present, vals, color=colors, edgecolor='white', height=0.6)

        # Ghi số lên bar
        for bar, val in zip(bars, vals):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                    f'{val:.1f}', va='center', fontsize=8, fontweight='bold')

        ax.set_xlabel("Avg PSNR (dB)", fontsize=9)
        ax.set_title(f'{case_name} — Method Comparison', fontsize=10, fontweight='bold')
        ax.set_xlim(20, max(vals) + 5)
        ax.grid(True, axis='x', alpha=0.3)

    fig5.suptitle('Comprehensive Comparison: Adaptive QP vs SVC vs Baselines\n'
                  'across 5 PU/BS Topologies',
                  fontsize=14, fontweight='bold')
    fig5.tight_layout(rect=[0, 0, 1, 0.96])
    path5 = str(RESULTS_DIR / "comprehensive_comparison.png")
    fig5.savefig(path5, dpi=150)
    print(f"  Saved: {path5}")

    # (Khong dung plt.show() theo yeu cau)
    # plt.show()
