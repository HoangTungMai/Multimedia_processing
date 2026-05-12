"""
================================================================================
H.264 Bitstream Decoder — UAV CR-NOMA Video Transmission
================================================================================

Chương trình decode các file bitstream H.264 (.264) từ 4 kịch bản quỹ đạo UAV.

Luồng hệ thống:
  UAV bay (trajectory) → Channel rate R(t) thay đổi → QP adaptation
  → H.264 encode trên UAV → Bitstream segments → Truyền về BS → BS decode

Chương trình này đóng vai trò **BS decoder**: nhận bitstream, giải mã, và
đánh giá chất lượng video nhận được theo từng kịch bản quỹ đạo.

Kịch bản:
  - circle:    Bay vòng tròn (QP cố định ~36, chất lượng thấp đều)
  - straight:  Bay thẳng A→B (QP thay đổi theo khoảng cách tới BS)
  - zigzag:    Bay zigzag (QP dao động mạnh)
  - optimized: Quỹ đạo tối ưu BCD+SCA (QP thích nghi tốt nhất)

Output:
  - decoded_output/<scenario>/ : Các frame đã decode (PNG)
  - decoded_output/comparison/ : Biểu đồ so sánh 4 kịch bản
  - Console: Thống kê chi tiết
================================================================================
"""

import os
import sys
import glob
import numpy as np
import cv2
import matplotlib.pyplot as plt
from pathlib import Path

# Thử load metadata từ .mat files
try:
    import scipy.io
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("⚠️  scipy không khả dụng — bỏ qua metadata .mat")

# ==============================================================================
# CẤU HÌNH
# ==============================================================================

BASE_DIR = Path(__file__).parent
BITSTREAM_DIR = BASE_DIR / "Bitstream"
OUTPUT_DIR = BASE_DIR / "decoded_output"
TEAMMATE_DIR = BASE_DIR / "output_for_teammate"

SCENARIOS = ["circle", "straight", "zigzag", "optimized"]

# Mapping tên thư mục → tên file .mat
MAT_MAPPING = {
    "circle":    "QP_circle.mat",
    "straight":  "QP_straight.mat",
    "zigzag":    "QP_zigzag.mat",
    "optimized": "QP_optimized.mat",
}

# ==============================================================================
# PHẦN 1: ĐỌC METADATA TỪ .MAT FILES
# ==============================================================================

def load_mat_metadata(scenario):
    """
    Đọc metadata QP/PSNR/SINR/Rate từ file .mat do teammate tạo.

    Returns:
        dict với keys: QP_selected, PSNR_est, R_UAV, SINR_dB, Layer, traj_name
        hoặc None nếu không đọc được
    """
    if not HAS_SCIPY:
        return None

    mat_file = TEAMMATE_DIR / MAT_MAPPING.get(scenario, "")
    if not mat_file.exists():
        return None

    try:
        raw = scipy.io.loadmat(str(mat_file))
        # Tìm key chứa metadata (có thể là 'metadata' hoặc 'meta')
        meta_key = None
        for k in raw:
            if not k.startswith('_'):
                meta_key = k
                break
        if meta_key is None:
            return None

        meta = raw[meta_key]
        # Trích xuất từ structured array
        record = meta[0, 0]
        field_names = meta.dtype.names

        result = {}
        for fname in field_names:
            val = record[fname]
            if isinstance(val, np.ndarray) and val.size > 1:
                result[fname] = val.flatten()
            elif isinstance(val, np.ndarray) and val.size == 1:
                result[fname] = val.flat[0]
            else:
                result[fname] = val

        return result
    except Exception as e:
        print(f"  ⚠️  Lỗi đọc {mat_file.name}: {e}")
        return None


# ==============================================================================
# PHẦN 2: DECODE H.264 BITSTREAM
# ==============================================================================

def decode_segment(seg_path, save_frames=True, output_dir=None, max_frames=None):
    """
    Decode một file bitstream H.264 (.264) bằng OpenCV.

    OpenCV sử dụng FFmpeg backend nội bộ để decode H.264 Annex B bitstream.
    Đây chính là chuẩn decode giống như khi encode trên UAV.

    Args:
        seg_path:    Đường dẫn tới file .264
        save_frames: Có lưu frame ra file PNG không
        output_dir:  Thư mục lưu frame
        max_frames:  Giới hạn số frame decode (None = tất cả)

    Returns:
        dict: {
            'file': tên file,
            'file_size': kích thước bytes,
            'num_frames': số frame decode được,
            'resolution': (width, height),
            'frames': list numpy arrays (nếu save_frames=False),
            'avg_brightness': độ sáng trung bình (proxy cho chất lượng),
            'spatial_detail': mức độ chi tiết không gian (Laplacian variance)
        }
    """
    cap = cv2.VideoCapture(str(seg_path))
    if not cap.isOpened():
        print(f"  ❌ Không thể mở: {seg_path}")
        return None

    frames = []
    brightness_values = []
    detail_values = []
    frame_idx = 0
    resolution = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if resolution is None:
            h, w = frame.shape[:2]
            resolution = (w, h)

        # Tính metrics chất lượng
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness_values.append(np.mean(gray))

        # Laplacian variance = đo mức chi tiết (QP cao → blur → variance thấp)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        detail_values.append(laplacian.var())

        # Lưu frame
        if save_frames and output_dir:
            os.makedirs(output_dir, exist_ok=True)
            fname = f"frame_{frame_idx:04d}.png"
            cv2.imwrite(str(Path(output_dir) / fname), frame)

        frames.append(frame)
        frame_idx += 1

        if max_frames and frame_idx >= max_frames:
            break

    cap.release()

    file_size = os.path.getsize(seg_path)

    return {
        'file': Path(seg_path).name,
        'file_size': file_size,
        'num_frames': frame_idx,
        'resolution': resolution,
        'frames': frames if not save_frames else [],
        'avg_brightness': np.mean(brightness_values) if brightness_values else 0,
        'spatial_detail': np.mean(detail_values) if detail_values else 0,
    }


def decode_scenario(scenario, save_frames=True, save_first_last=True):
    """
    Decode tất cả segments của một kịch bản quỹ đạo.

    Args:
        scenario: tên kịch bản (circle/straight/zigzag/optimized)
        save_frames: lưu tất cả frame
        save_first_last: chỉ lưu frame đầu+cuối mỗi segment (tiết kiệm disk)

    Returns:
        list[dict]: kết quả decode cho từng segment
    """
    scenario_dir = BITSTREAM_DIR / scenario
    if not scenario_dir.exists():
        print(f"  ❌ Không tìm thấy: {scenario_dir}")
        return []

    # Tìm và sắp xếp các file .264
    seg_files = sorted(scenario_dir.glob("seg_*.264"),
                       key=lambda f: int(f.stem.split('_')[1]))

    if not seg_files:
        print(f"  ❌ Không có file .264 trong {scenario_dir}")
        return []

    results = []
    out_dir = OUTPUT_DIR / scenario if save_frames else None

    for seg_file in seg_files:
        seg_out = (OUTPUT_DIR / scenario / seg_file.stem) if save_first_last else None

        info = decode_segment(
            seg_file,
            save_frames=False,  # Không lưu hết, chỉ phân tích
            output_dir=None,
        )
        if info is None:
            continue

        # Lưu frame đầu và cuối để minh họa
        if save_first_last and info['frames']:
            sample_dir = OUTPUT_DIR / scenario / "samples"
            os.makedirs(sample_dir, exist_ok=True)
            seg_name = seg_file.stem

            # Frame đầu
            cv2.imwrite(str(sample_dir / f"{seg_name}_first.png"),
                        info['frames'][0])
            # Frame cuối
            if len(info['frames']) > 1:
                cv2.imwrite(str(sample_dir / f"{seg_name}_last.png"),
                            info['frames'][-1])

        # Giải phóng bộ nhớ frame
        info['frames'] = []
        results.append(info)

    return results


# ==============================================================================
# PHẦN 3: PHÂN TÍCH VÀ SO SÁNH
# ==============================================================================

def print_scenario_report(scenario, segments, metadata=None):
    """In báo cáo chi tiết cho một kịch bản."""
    print(f"\n{'='*70}")
    print(f"  📊 KỊch bản: {scenario.upper()}")
    if metadata and 'traj_name' in metadata:
        traj = metadata['traj_name']
        if isinstance(traj, np.ndarray):
            traj = str(traj.flat[0]) if traj.size > 0 else str(traj)
        print(f"  Quỹ đạo: {traj}")
    print(f"{'='*70}")

    total_size = 0
    total_frames = 0

    header = f"{'Seg':>6} | {'Size':>10} | {'Frames':>6} | {'Detail':>10}"
    if metadata and 'QP_selected' in metadata:
        header += f" | {'QP':>4} | {'PSNR_est':>9} | {'SINR_dB':>8} | {'Layer':>5}"
    print(header)
    print("-" * len(header))

    for i, seg in enumerate(segments):
        size_kb = seg['file_size'] / 1024
        total_size += seg['file_size']
        total_frames += seg['num_frames']

        line = (f"{seg['file']:>6} | {size_kb:>8.1f}KB | {seg['num_frames']:>6} | "
                f"{seg['spatial_detail']:>10.1f}")

        if metadata and 'QP_selected' in metadata:
            qp_arr = metadata['QP_selected']
            psnr_arr = metadata.get('PSNR_est', np.zeros(10))
            sinr_arr = metadata.get('SINR_dB', np.zeros(10))
            layer_arr = metadata.get('Layer', np.zeros(10))

            if i < len(qp_arr):
                qp_val = int(qp_arr[i]) if not np.isnan(qp_arr[i]) else -1
                psnr_val = float(psnr_arr[i]) if i < len(psnr_arr) else 0
                sinr_val = float(sinr_arr[i]) if i < len(sinr_arr) else 0
                layer_val = int(layer_arr[i]) if i < len(layer_arr) else 0
                line += f" | {qp_val:>4} | {psnr_val:>7.2f}dB | {sinr_val:>6.2f}dB | {layer_val:>5}"

        print(line)

    print(f"\n  📦 Tổng: {total_size/1024:.1f} KB | {total_frames} frames")
    if segments and segments[0]['resolution']:
        print(f"  📐 Resolution: {segments[0]['resolution'][0]}×{segments[0]['resolution'][1]} (CIF)")

    return total_size, total_frames


def plot_comparison(all_results, all_metadata):
    """
    Tạo biểu đồ so sánh 4 kịch bản:
    - Bitrate per segment
    - Spatial detail (proxy PSNR)
    - QP selected (từ metadata)
    - PSNR estimated (từ metadata)
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle("So sánh Chất lượng Video — 4 Kịch bản Quỹ đạo UAV\n"
                 "(H.264 Decode tại Base Station)",
                 fontsize=14, fontweight='bold')

    colors = {'circle': '#E91E63', 'straight': '#2196F3',
              'zigzag': '#FF9800', 'optimized': '#4CAF50'}
    markers = {'circle': 'o', 'straight': 's', 'zigzag': '^', 'optimized': 'D'}
    x = np.arange(1, 11)

    # ── Subplot 1: Bitrate (file size per segment) ──
    ax = axes[0, 0]
    for sc in SCENARIOS:
        if sc not in all_results:
            continue
        sizes = [s['file_size'] / 1024 for s in all_results[sc]]
        ax.plot(x[:len(sizes)], sizes, f'-{markers[sc]}', color=colors[sc],
                ms=6, lw=2, label=sc.capitalize())
    ax.set_xlabel("Segment"); ax.set_ylabel("Kích thước (KB)")
    ax.set_title("Bitrate theo Segment (kích thước file)")
    ax.legend(); ax.grid(True, alpha=0.3)
    ax.set_yscale('log')

    # ── Subplot 2: Spatial Detail (Laplacian Variance) ──
    ax = axes[0, 1]
    for sc in SCENARIOS:
        if sc not in all_results:
            continue
        details = [s['spatial_detail'] for s in all_results[sc]]
        ax.plot(x[:len(details)], details, f'-{markers[sc]}', color=colors[sc],
                ms=6, lw=2, label=sc.capitalize())
    ax.set_xlabel("Segment"); ax.set_ylabel("Laplacian Variance")
    ax.set_title("Mức Chi Tiết Không Gian (cao = sắc nét)")
    ax.legend(); ax.grid(True, alpha=0.3)

    # ── Subplot 3: QP Selected (từ metadata) ──
    ax = axes[1, 0]
    has_qp = False
    for sc in SCENARIOS:
        meta = all_metadata.get(sc)
        if meta and 'QP_selected' in meta:
            qp = meta['QP_selected']
            ax.plot(x[:len(qp)], qp, f'-{markers[sc]}', color=colors[sc],
                    ms=6, lw=2, label=sc.capitalize())
            has_qp = True
    if has_qp:
        ax.set_xlabel("Segment"); ax.set_ylabel("QP")
        ax.set_title("Quantization Parameter (thấp = chất lượng cao)")
        ax.invert_yaxis()
        ax.legend(); ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, "Không có metadata QP", transform=ax.transAxes,
                ha='center', va='center', fontsize=14)

    # ── Subplot 4: PSNR Estimated ──
    ax = axes[1, 1]
    has_psnr = False
    for sc in SCENARIOS:
        meta = all_metadata.get(sc)
        if meta and 'PSNR_est' in meta:
            psnr = meta['PSNR_est']
            ax.plot(x[:len(psnr)], psnr, f'-{markers[sc]}', color=colors[sc],
                    ms=6, lw=2, label=sc.capitalize())
            has_psnr = True
    if has_psnr:
        ax.set_xlabel("Segment"); ax.set_ylabel("PSNR (dB)")
        ax.set_title("PSNR Ước lượng (cao = chất lượng tốt)")
        ax.legend(); ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, "Không có metadata PSNR", transform=ax.transAxes,
                ha='center', va='center', fontsize=14)

    plt.tight_layout()
    comp_dir = OUTPUT_DIR / "comparison"
    os.makedirs(comp_dir, exist_ok=True)
    save_path = comp_dir / "video_quality_comparison.png"
    plt.savefig(str(save_path), dpi=150, bbox_inches='tight')
    plt.close()
    print(f"\n📊 Biểu đồ so sánh: {save_path}")


def plot_sample_frames(all_results):
    """Hiển thị frame đầu tiên từ mỗi segment cho 4 kịch bản."""
    fig, axes = plt.subplots(4, 5, figsize=(20, 14))
    fig.suptitle("Frame Mẫu — 5 Segments đầu × 4 Kịch bản",
                 fontsize=14, fontweight='bold')

    for row, sc in enumerate(SCENARIOS):
        sample_dir = OUTPUT_DIR / sc / "samples"
        for col in range(5):
            ax = axes[row, col]
            seg_name = f"seg_{col+1:03d}"
            img_path = sample_dir / f"{seg_name}_first.png"

            if img_path.exists():
                img = cv2.imread(str(img_path))
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                ax.imshow(img_rgb)
            else:
                ax.text(0.5, 0.5, "N/A", transform=ax.transAxes,
                        ha='center', va='center')

            ax.set_xticks([]); ax.set_yticks([])
            if col == 0:
                ax.set_ylabel(sc.capitalize(), fontsize=12, fontweight='bold')
            if row == 0:
                ax.set_title(f"Seg {col+1}", fontsize=10)

    plt.tight_layout()
    save_path = OUTPUT_DIR / "comparison" / "sample_frames.png"
    plt.savefig(str(save_path), dpi=120, bbox_inches='tight')
    plt.close()
    print(f"🖼️  Frame mẫu: {save_path}")


# ==============================================================================
# PHẦN 4: MAIN
# ==============================================================================

def main():
    print("=" * 70)
    print("  🎬 H.264 BITSTREAM DECODER — UAV CR-NOMA Video Transmission")
    print("  📡 Mô phỏng decode tại Base Station (BS)")
    print("=" * 70)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_results = {}
    all_metadata = {}

    # 1. Decode từng kịch bản
    for scenario in SCENARIOS:
        print(f"\n🔄 Đang decode kịch bản: {scenario}...")

        # Load metadata
        metadata = load_mat_metadata(scenario)
        all_metadata[scenario] = metadata

        # Decode segments
        segments = decode_scenario(scenario, save_frames=False, save_first_last=True)
        if not segments:
            continue
        all_results[scenario] = segments

        # In báo cáo
        print_scenario_report(scenario, segments, metadata)

    # 2. Tổng hợp so sánh
    if len(all_results) >= 2:
        print(f"\n\n{'='*70}")
        print(f"  📊 TỔNG HỢP SO SÁNH 4 KỊCH BẢN")
        print(f"{'='*70}")

        summary_data = []
        for sc in SCENARIOS:
            if sc not in all_results:
                continue
            segs = all_results[sc]
            total_size = sum(s['file_size'] for s in segs)
            avg_detail = np.mean([s['spatial_detail'] for s in segs])
            total_frames = sum(s['num_frames'] for s in segs)

            meta = all_metadata.get(sc)
            avg_psnr = np.mean(meta['PSNR_est']) if meta and 'PSNR_est' in meta else 0
            avg_qp = np.mean(meta['QP_selected']) if meta and 'QP_selected' in meta else 0

            summary_data.append({
                'scenario': sc,
                'total_size': total_size,
                'total_frames': total_frames,
                'avg_detail': avg_detail,
                'avg_psnr': avg_psnr,
                'avg_qp': avg_qp,
            })

        print(f"\n{'Kịch bản':<12} | {'Tổng Size':>10} | {'Frames':>6} | "
              f"{'Avg Detail':>10} | {'Avg QP':>6} | {'Avg PSNR':>9}")
        print("-" * 72)
        for s in summary_data:
            print(f"{s['scenario']:<12} | {s['total_size']/1024:>8.1f}KB | "
                  f"{s['total_frames']:>6} | {s['avg_detail']:>10.1f} | "
                  f"{s['avg_qp']:>6.1f} | {s['avg_psnr']:>7.2f}dB")

        # Tìm kịch bản tốt nhất
        best = max(summary_data, key=lambda x: x['avg_psnr'] if x['avg_psnr'] > 0
                   else x['avg_detail'])
        print(f"\n  🏆 Kịch bản tốt nhất: {best['scenario'].upper()}")
        if best['avg_psnr'] > 0:
            print(f"     PSNR trung bình: {best['avg_psnr']:.2f} dB")

    # 3. Tạo biểu đồ
    print("\n📈 Đang tạo biểu đồ so sánh...")
    plot_comparison(all_results, all_metadata)
    if all_results:
        plot_sample_frames(all_results)

    print(f"\n✅ Hoàn tất! Kết quả tại: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
