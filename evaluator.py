"""
================================================================================
H.264 Quality Evaluator — UAV CR-NOMA Video Transmission
================================================================================
Giải mã bitstream .264 và tính PSNR thực tế (Full-Reference) so với video gốc.
Vẽ biểu đồ so sánh 3 kịch bản: Optimized, Straight, Circle.

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

    def evaluate_scenario(self, folder_path, label):
        print(f"  Decoding {label}...")
        frames = self.decode_folder(folder_path)
        psnrs = []
        num_frames = min(len(self.original_frames), len(frames))
        for i in range(num_frames):
            psnrs.append(self.calculate_psnr(
                self.original_frames[i], frames[i]))

        avg_psnr = np.mean(psnrs)
        min_psnr = np.min(psnrs)
        max_psnr = np.max(psnrs)
        print(f"    Avg PSNR: {avg_psnr:.2f} dB "
              f"(Min: {min_psnr:.2f}, Max: {max_psnr:.2f})")
        return psnrs, avg_psnr


if __name__ == "__main__":
    print("=" * 60)
    print(" UAV CR-NOMA Video Quality Evaluation")
    print("=" * 60)

    evaluator = QualityEvaluator(YUV_PATH)

    scenarios = {
        "Optimized (BCD+SCA)": str(BITSTREAM_DIR / "Optimized"),
        "Straight Line": str(BITSTREAM_DIR / "Straight"),
        "Circle": str(BITSTREAM_DIR / "Circle"),
    }

    print("\n[Step 1] Evaluating PSNR...")
    all_results = {}
    for label, folder in scenarios.items():
        if not os.path.exists(folder):
            print(f"  [SKIP] {label}: folder not found ({folder})")
            continue
        psnrs, avg = evaluator.evaluate_scenario(folder, label)
        all_results[label] = (psnrs, avg)

    # Vẽ biểu đồ
    print("\n[Step 2] Generating comparison plot...")
    colors = {'Optimized (BCD+SCA)': '#2196F3',
              'Straight Line': '#FF9800',
              'Circle': '#4CAF50'}

    fig, ax = plt.subplots(figsize=(12, 6))
    for label, (psnrs, avg) in all_results.items():
        color = colors.get(label, 'gray')
        ax.plot(psnrs, label=f"{label} (Avg: {avg:.2f} dB)",
                color=color, linewidth=1.5, alpha=0.85)

    ax.set_title('Video Quality Comparison: PSNR per Frame\n'
                 'UAV CR-NOMA Uplink (BCD+SCA vs Baselines)',
                 fontsize=13, fontweight='bold')
    ax.set_xlabel('Frame Index', fontsize=11)
    ax.set_ylabel('PSNR (dB)', fontsize=11)
    ax.grid(True, linestyle='--', alpha=0.4)
    ax.legend(fontsize=10, loc='lower right')
    fig.tight_layout()

    output_path = str(RESULTS_DIR / "comparison_all_scenarios.png")
    fig.savefig(output_path, dpi=150)
    print(f"  Saved: {output_path}")

    # Bảng tổng kết
    print("\n" + "=" * 60)
    print(f" {'Scenario':<25} {'Avg PSNR':>10} {'Gain vs Straight':>18}")
    print("-" * 60)
    baseline_psnr = all_results.get("Straight Line", ([], 0))[1]
    for label, (_, avg) in all_results.items():
        gain = avg - baseline_psnr
        print(f" {label:<25} {avg:>8.2f} dB {gain:>+15.2f} dB")
    print("=" * 60)
