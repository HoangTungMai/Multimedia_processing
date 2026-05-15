"""
================================================================================
H.264 Adaptive Encoder — UAV CR-NOMA Video Transmission
================================================================================
Nén video foreman_cif.yuv bằng FFmpeg (libx264) với QP thích nghi theo
Rate R(t) từ thuật toán tối ưu BCD+SCA.

Hỗ trợ nhiều tổ hợp vị trí PU/BS để chứng minh tính tổng quát của thuật toán.

Cách chạy:
  python encoder.py
================================================================================
"""

import os
import subprocess
import numpy as np
import imageio_ffmpeg
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.optimize import minimize

BASE_DIR = Path(__file__).parent
BITSTREAM_DIR = BASE_DIR / "results" / "bitstreams"
RESULTS_DIR = BASE_DIR / "results"
YUV_PATH = BASE_DIR / "foreman_cif.yuv"

# ==============================================================================
# CÁC CẤU HÌNH VỊ TRÍ PU/BS
# ==============================================================================

CONFIGS = {
    "Case1_Default": {
        "desc": "PU giua, BS canh (Mac dinh)",
        "q_A": [0.0, 0.0], "q_B": [200.0, 200.0],
        "w_BS": [200.0, 0.0], "w_PU": [100.0, 100.0],
    },
    "Case2_BS_Far": {
        "desc": "BS o xa, PU gan BS",
        "q_A": [0.0, 0.0], "q_B": [200.0, 200.0],
        "w_BS": [300.0, 50.0], "w_PU": [250.0, 80.0],
    },
    "Case3_Opposite": {
        "desc": "PU va BS doi dien nhau",
        "q_A": [0.0, 0.0], "q_B": [200.0, 200.0],
        "w_BS": [50.0, 200.0], "w_PU": [200.0, 50.0],
    },
    "Case4_PU_Near_Start": {
        "desc": "PU gan diem xuat phat A",
        "q_A": [0.0, 0.0], "q_B": [200.0, 200.0],
        "w_BS": [200.0, 0.0], "w_PU": [30.0, 30.0],
    },
}

# ==============================================================================
# THAM SỐ CHUNG
# ==============================================================================
H = 100.0; N = 30; T = 30.0; dt = T / N
V_max = 15.0; D_max = V_max * dt
P_max = 0.5; P_pu = 0.3
beta0 = 1e-4; sigma2 = 1e-11
I_th = 5e-11; R_pu_min = 0.5
w0, w1, alpha_q = 0.6, 0.4, 5.0
R_BL, R_EL = 2.0, 1.0
P_safe = 0.005  # Công suất an toàn cho baseline


# ==============================================================================
# BỘ NÉN VIDEO
# ==============================================================================

class VideoEncoder:
    def __init__(self, yuv_path, width=352, height=288):
        self.yuv_path = str(yuv_path)
        self.width = width
        self.height = height
        self.frame_size = int(width * height * 1.5)
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        # R-Q Model parameters (Ma, Siwei et al. 2005)
        self.X1 = 0.85   # Hệ số bậc 1
        self.X2 = 0.1    # Hệ số bậc 2
        self.W = 4       # Hệ số bandwidth hiệu dụng
        self.T_slot = T / N  # Thời gian 1 slot (s)
        self.fps = 10    # Frames per slot
        # Tính MAD cho từng slot
        print("  Computing MAD per slot (R-Q Model)...")
        self.slot_mad = self._compute_slot_mad()
        print(f"  MAD range: {min(self.slot_mad):.2f} ~ {max(self.slot_mad):.2f}")

    def _compute_slot_mad(self):
        """Tính Mean Absolute Difference cho mỗi slot (10 frames/slot)."""
        frames = []
        with open(self.yuv_path, 'rb') as f:
            while True:
                data = f.read(self.frame_size)
                if not data:
                    break
                y_plane = np.frombuffer(data[:self.width * self.height], dtype=np.uint8)
                frames.append(y_plane.astype(np.float32))

        slot_mad = []
        for slot in range(N):
            start = slot * self.fps
            end = min(start + self.fps, len(frames))
            mad_vals = []
            for i in range(start, end):
                if i == 0:
                    mad = np.mean(np.abs(frames[i] - 128.0))
                else:
                    mad = np.mean(np.abs(frames[i] - frames[i - 1]))
                mad_vals.append(mad)
            slot_mad.append(np.mean(mad_vals))
        return slot_mad

    def rate_to_qp(self, rate, slot_idx=0):
        """R-Q Model: Channel Rate → Qstep → QP (Ma, Siwei 2005).

        R_frame = MAD × (X1/Qstep + X2/Qstep²)
        Qstep = 2^((QP-4)/6)
        """
        # Bits khả dụng mỗi frame
        bits_per_frame = self.W * rate * self.T_slot / self.fps
        mad = self.slot_mad[min(slot_idx, len(self.slot_mad) - 1)]

        if mad < 0.01 or bits_per_frame <= 0:
            return 32  # Fallback

        # Giải: bits = MAD × (X1/Qstep + X2/Qstep²)
        # Đặt u = 1/Qstep → MAD·X2·u² + MAD·X1·u - bits = 0
        a = mad * self.X2
        b = mad * self.X1
        c = -bits_per_frame

        discriminant = b ** 2 - 4 * a * c
        if discriminant < 0:
            return 32

        u = (-b + np.sqrt(discriminant)) / (2 * a)
        if u <= 0:
            return 32

        Qstep = 1.0 / u
        QP = int(round(6 * np.log2(max(Qstep, 1.0)) + 4))
        return int(np.clip(QP, 10, 51))

    def get_segment_frames(self, start_frame, num_frames):
        with open(self.yuv_path, 'rb') as f:
            f.seek(start_frame * self.frame_size)
            return f.read(num_frames * self.frame_size)

    def encode_gop(self, frames_data, output_path, qp):
        cmd = [
            self.ffmpeg_exe, '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-s', f'{self.width}x{self.height}', '-pix_fmt', 'yuv420p',
            '-i', '-', '-c:v', 'libx264', '-qp', str(qp),
            '-g', '10', '-frames:v', '10', output_path
        ]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        process.communicate(input=frames_data)

    def encode_scenario(self, rates, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        total_size = 0
        for i, r in enumerate(rates):
            qp = self.rate_to_qp(r, slot_idx=i)
            output_path = os.path.join(output_dir, f"slot_{i+1:03d}.264")
            frames_data = self.get_segment_frames(i * 10, 10)
            self.encode_gop(frames_data, output_path, qp)
            total_size += os.path.getsize(output_path) / 1024
        return total_size

    def encode_svc(self, rates, output_dir, qp_bl=35, qp_el=15):
        """
        SVC 2-Layer Encoding (Residual-based):
          - Base Layer (BL): Nén video gốc với QP cao → video mờ, nhẹ
          - Enhancement Layer (EL): Nén phần SAI KHÁC (residual = gốc - BL)
            → BL + EL = video nét (giống SVC chuẩn H.264 Annex G)
        """
        bl_dir = os.path.join(output_dir, "BL")
        el_dir = os.path.join(output_dir, "EL")
        os.makedirs(bl_dir, exist_ok=True)
        os.makedirs(el_dir, exist_ok=True)

        total_bl, total_el = 0, 0
        for i in range(len(rates)):
            frames_data = self.get_segment_frames(i * 10, 10)

            # --- Base Layer: nén video gốc ---
            bl_path = os.path.join(bl_dir, f"slot_{i+1:03d}.264")
            self.encode_gop(frames_data, bl_path, qp_bl)
            total_bl += os.path.getsize(bl_path) / 1024

            # --- Decode BL để tính residual ---
            import cv2
            cap = cv2.VideoCapture(bl_path)
            bl_frames = []
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                bl_frames.append(frame)
            cap.release()

            # --- Tính Residual: (Original - BL_decoded) + 128 ---
            # Đọc 10 frames gốc từ YUV
            orig_frames = []
            with open(self.yuv_path, 'rb') as f:
                f.seek(i * 10 * self.frame_size)
                for _ in range(10):
                    data = f.read(self.frame_size)
                    if not data:
                        break
                    yuv = np.frombuffer(data, dtype=np.uint8).reshape(
                        (int(self.height * 1.5), self.width))
                    bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
                    orig_frames.append(bgr)

            # Tạo YUV residual để encode
            n_frames = min(len(orig_frames), len(bl_frames))
            residual_yuv = bytearray()
            for j in range(n_frames):
                # Residual + 128 (shift để nằm trong [0, 255])
                res = np.clip(
                    orig_frames[j].astype(np.int16) - bl_frames[j].astype(np.int16) + 128,
                    0, 255
                ).astype(np.uint8)
                # Convert BGR → YUV420 để FFmpeg đọc
                yuv_frame = cv2.cvtColor(res, cv2.COLOR_BGR2YUV_I420)
                residual_yuv.extend(yuv_frame.tobytes())

            # --- Enhancement Layer: nén residual ---
            el_path = os.path.join(el_dir, f"slot_{i+1:03d}.264")
            cmd = [
                self.ffmpeg_exe, '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo',
                '-s', f'{self.width}x{self.height}', '-pix_fmt', 'yuv420p',
                '-i', '-', '-c:v', 'libx264', '-qp', str(qp_el),
                '-g', '10', '-frames:v', str(n_frames), el_path
            ]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            process.communicate(input=bytes(residual_yuv))
            total_el += os.path.getsize(el_path) / 1024

        print(f"      BL (QP={qp_bl}): {total_bl:.1f} KB")
        print(f"      EL residual (QP={qp_el}): {total_el:.1f} KB")
        print(f"      Total SVC: {total_bl + total_el:.1f} KB")
        return total_bl, total_el


# ==============================================================================
# BỘ TỐI ƯU BCD+SCA (Tham số hóa vị trí PU/BS)
# ==============================================================================

def run_bcd_sca(q_A, q_B, w_BS, w_PU, qoe_mode='sigmoid'):
    """Chạy BCD+SCA với bộ tọa độ PU/BS tùy ý.
    qoe_mode: 'sigmoid' (Double Sigmoid cho SVC) hoặc 'log' (Logarithmic cho Adaptive QP)
    Trả về (rates, trajectory, power)."""
    q_A, q_B = np.array(q_A), np.array(q_B)
    w_BS, w_PU = np.array(w_BS), np.array(w_PU)

    def h_uav(q): return beta0 / (np.sum((q - w_BS)**2) + H**2)
    def g_pu(q):  return beta0 / (np.sum((q - w_PU)**2) + H**2)
    h_pu_val = beta0 / np.sum((w_PU - w_BS)**2)
    def rate_uav(p, q): return np.log2(1 + p * h_uav(q) / sigma2)

    def qoe_sigmoid(R):
        return w0/(1+np.exp(-alpha_q*(R - R_BL))) + w1/(1+np.exp(-alpha_q*(R - (R_BL+R_EL))))

    def qoe_log(R):
        return np.log2(1 + max(R, 0))

    qoe_slot = qoe_sigmoid if qoe_mode == 'sigmoid' else qoe_log

    def solve_power(traj):
        p = np.zeros(N)
        gamma_min = 2**R_pu_min - 1
        for n in range(N):
            p_interf = I_th / g_pu(traj[n])
            h_n = h_uav(traj[n])
            p_pu_qos = P_pu * h_pu_val / (gamma_min * h_n) - sigma2 / h_n
            p[n] = max(0, min(P_max, p_interf, max(0, p_pu_qos)))
        return p

    def solve_trajectory(p, traj_k):
        x0 = traj_k.flatten()
        def obj(x):
            traj = x.reshape((N, 2))
            neg_qoe = 0
            for n in range(N):
                dk2 = np.sum((traj_k[n] - w_BS)**2) + H**2
                A = p[n] * beta0 / sigma2
                R_k = np.log2(1 + A / dk2)
                dR = -A * np.log2(np.e) / (dk2 * (dk2 + A))
                d2 = np.sum((traj[n] - w_BS)**2) + H**2
                R_lb = R_k + dR * (d2 - dk2)
                neg_qoe -= qoe_slot(R_lb)
            return neg_qoe
        def cons(x):
            traj = x.reshape((N, 2))
            c = [D_max**2 - np.sum((traj[0] - q_A)**2)]
            for n in range(N-1):
                c.append(D_max**2 - np.sum((traj[n+1] - traj[n])**2))
            c.append(D_max**2 - np.sum((q_B - traj[-1])**2))
            for n in range(N):
                if p[n] < 1e-15: c.append(1.0); continue
                Ds = p[n] * beta0 / I_th - H**2
                if Ds < 0: c.append(1.0); continue
                qk = traj_k[n] - w_PU
                c.append(np.sum(qk**2) + 2*np.dot(qk, traj[n]-traj_k[n]) - Ds)
            return np.array(c)
        res = minimize(obj, x0, method='SLSQP',
                       constraints={'type':'ineq','fun':cons}, options={'maxiter':80})
        return res.x.reshape((N, 2))

    # Main BCD Loop
    traj = np.array([q_A + (q_B-q_A)*(n+1)/(N+1) for n in range(N)])
    p = np.ones(N) * 0.01
    qoe_history = []
    for it in range(8):
        p = solve_power(traj)
        traj = solve_trajectory(p, traj)
        qoe_val = sum(qoe_slot(rate_uav(p[n], traj[n])) for n in range(N))
        qoe_history.append(qoe_val)
        print(f"      Iter {it+1}: QoE = {qoe_val:.4f}")

    rates = [rate_uav(p[n], traj[n]) for n in range(N)]
    return rates, traj, p, qoe_history


def compute_straight_rates(q_A, q_B, w_BS):
    """Tính Rate cho baseline Straight Line với công suất an toàn."""
    q_A, q_B, w_BS = np.array(q_A), np.array(q_B), np.array(w_BS)
    def h_uav(q): return beta0 / (np.sum((q - w_BS)**2) + H**2)
    def rate_uav(p, q): return np.log2(1 + p * h_uav(q) / sigma2)
    traj = np.array([q_A + (q_B-q_A)*(n+1)/(N+1) for n in range(N)])
    return [rate_uav(P_safe, q) for q in traj], traj


def compute_circle_rates(q_A, q_B, w_BS):
    """Tính Rate cho baseline Circle: bay vòng tròn từ A đến B."""
    q_A, q_B, w_BS = np.array(q_A), np.array(q_B), np.array(w_BS)
    def h_uav(q): return beta0 / (np.sum((q - w_BS)**2) + H**2)
    def rate_uav(p, q): return np.log2(1 + p * h_uav(q) / sigma2)
    # Tâm vòng tròn = trung điểm A-B, bán kính = nửa khoảng cách A-B
    center = (q_A + q_B) / 2
    radius = np.linalg.norm(q_B - q_A) / 2
    # Góc bắt đầu từ A, kết thúc tại B
    angle_start = np.arctan2(q_A[1] - center[1], q_A[0] - center[0])
    angle_end = angle_start + np.pi  # Nửa vòng tròn
    angles = np.linspace(angle_start, angle_end, N)
    traj = np.array([center + radius * np.array([np.cos(a), np.sin(a)]) for a in angles])
    return [rate_uav(P_safe, q) for q in traj], traj


# ==============================================================================
# VẼ QUỸ ĐẠO
# ==============================================================================

def plot_all_trajectories(all_results):
    """Vẽ quỹ đạo tối ưu cho tất cả các cấu hình PU/BS (2×2 grid)."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()

    for idx, (case_name, data) in enumerate(all_results.items()):
        ax = axes[idx]
        cfg = data["config"]
        traj = data["trajectory"]
        q_A = np.array(cfg["q_A"]); q_B = np.array(cfg["q_B"])
        w_BS = np.array(cfg["w_BS"]); w_PU = np.array(cfg["w_PU"])

        # Quỹ đạo tối ưu (Sigmoid QoE)
        ax.plot(traj[:, 0], traj[:, 1], 'b-o', ms=3, lw=1.5, label='Sigmoid QoE')
        # Quỹ đạo Log QoE
        if "traj_log" in data:
            traj_log = data["traj_log"]
            ax.plot(traj_log[:, 0], traj_log[:, 1], '-s', color='#FF5722',
                    ms=3, lw=1.5, alpha=0.8, label='Log QoE')
        # Đường thẳng A→B
        traj_s = data["traj_straight"]
        ax.plot(traj_s[:, 0], traj_s[:, 1], '--', color='orange', alpha=0.5, label='Straight')
        # Vòng tròn
        traj_c = data["traj_circle"]
        ax.plot(traj_c[:, 0], traj_c[:, 1], ':', color='green', alpha=0.5, label='Circle')
        # Các điểm
        ax.plot(*q_A, 'gs', ms=12, zorder=5)
        ax.plot(*q_B, 'g^', ms=12, zorder=5)
        ax.plot(*w_BS, 'kD', ms=10, label='BS', zorder=5)
        ax.plot(*w_PU, 'r^', ms=12, label='PU', zorder=5)
        ax.add_patch(plt.Circle(w_PU, 30, color='r', fill=True, alpha=0.1))

        ax.set_title(f"{case_name}\n{cfg['desc']}", fontsize=10)
        ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)")
        ax.legend(fontsize=6, loc='best')
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal')

    fig.suptitle("UAV Trajectory Optimization — Different PU/BS Configurations",
                 fontsize=14, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    path = str(RESULTS_DIR / "trajectories_all_cases.png")
    fig.savefig(path, dpi=150)
    print(f"  Saved trajectory plot: {path}")


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print(" UAV CR-NOMA H.264 Adaptive Encoder")
    print(" Multi-Configuration Benchmark")
    print("=" * 60)

    encoder = VideoEncoder(YUV_PATH)
    all_results = {}

    for case_name, cfg in CONFIGS.items():
        print(f"\n{'='*60}")
        print(f"  {case_name}: {cfg['desc']}")
        print(f"  BS={cfg['w_BS']}, PU={cfg['w_PU']}")
        print(f"{'='*60}")

        # 1. Chạy BCD+SCA (Sigmoid QoE)
        print("    [Optimized - Sigmoid QoE] Running BCD+SCA...")
        opt_rates, traj, power, qoe_hist_sig = run_bcd_sca(
            cfg["q_A"], cfg["q_B"], cfg["w_BS"], cfg["w_PU"], qoe_mode='sigmoid')
        avg_opt = np.mean(opt_rates)

        # 2. Chạy BCD+SCA (Log QoE) — tối ưu cho Adaptive QP
        print("    [Opt_LogQoE - Log QoE] Running BCD+SCA...")
        log_rates, traj_log, power_log, qoe_hist_log = run_bcd_sca(
            cfg["q_A"], cfg["q_B"], cfg["w_BS"], cfg["w_PU"], qoe_mode='log')
        avg_log = np.mean(log_rates)

        # 3. Baseline Straight
        straight_rates, traj_s = compute_straight_rates(
            cfg["q_A"], cfg["q_B"], cfg["w_BS"])
        avg_straight = np.mean(straight_rates)

        # 4. Baseline Circle
        circle_rates, traj_c = compute_circle_rates(
            cfg["q_A"], cfg["q_B"], cfg["w_BS"])
        avg_circle = np.mean(circle_rates)

        print(f"    Avg Rate: Sigmoid={avg_opt:.2f}, Log={avg_log:.2f}, Straight={avg_straight:.2f}, Circle={avg_circle:.2f}")

        # 5. Encode Adaptive QP (dùng Log QoE rates — PSNR tốt hơn)
        print("    Encoding Adaptive_QP...")
        sz_aqp = encoder.encode_scenario(
            log_rates, str(BITSTREAM_DIR / case_name / "Adaptive_QP"))
        print(f"      Size: {sz_aqp:.1f} KB")

        print("    Encoding Straight...")
        sz_straight = encoder.encode_scenario(
            straight_rates, str(BITSTREAM_DIR / case_name / "Straight"))
        print(f"      Size: {sz_straight:.1f} KB")

        print("    Encoding Circle...")
        sz_circle = encoder.encode_scenario(
            circle_rates, str(BITSTREAM_DIR / case_name / "Circle"))
        print(f"      Size: {sz_circle:.1f} KB")

        # 6. SVC 2-Layer (dùng cùng rates)
        print("    Encoding SVC (BL+EL)...")
        encoder.encode_svc(
            log_rates, str(BITSTREAM_DIR / case_name / "SVC"))

        # Lưu rates để evaluator biết chọn lớp nào
        import json
        rates_path = str(BITSTREAM_DIR / case_name / "opt_rates.json")
        with open(rates_path, 'w') as f:
            json.dump(log_rates, f)

        all_results[case_name] = {
            "config": cfg,
            "opt_rates": opt_rates,
            "log_rates": log_rates,
            "straight_rates": straight_rates,
            "circle_rates": circle_rates,
            "trajectory": traj,
            "traj_log": traj_log,
            "traj_straight": traj_s,
            "traj_circle": traj_c,
            "power": power,
            "power_log": power_log,
            "qoe_hist_sig": qoe_hist_sig,
            "qoe_hist_log": qoe_hist_log,
        }

    # 7. Vẽ quỹ đạo
    print("\n[Plotting trajectories...]")
    plot_all_trajectories(all_results)

    # 8. Vẽ BCD Convergence Curve
    print("[Plotting BCD convergence...]")
    n_cases = len(all_results)
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.flatten()
    for idx, (case_name, data) in enumerate(all_results.items()):
        ax = axes[idx]
        iters = range(1, 9)
        ax.plot(iters, data["qoe_hist_sig"], '-o', color='#2196F3',
                ms=5, lw=2, label='Sigmoid QoE')
        ax.plot(iters, data["qoe_hist_log"], '-s', color='#FF5722',
                ms=5, lw=2, label='Log QoE')
        ax.set_xlabel('BCD Iteration', fontsize=10)
        ax.set_ylabel('Total QoE', fontsize=10)
        ax.set_title(case_name, fontsize=10, fontweight='bold')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_xticks(range(1, 9))
    fig.suptitle('BCD+SCA Convergence: QoE vs Iteration',
                 fontsize=13, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    conv_path = str(RESULTS_DIR / "bcd_convergence.png")
    fig.savefig(conv_path, dpi=150)
    print(f"  Saved: {conv_path}")

    # 9. Vẽ Power & Rate (2×2)
    print("[Plotting power & rate...]")
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    axes = axes.flatten()
    t_slots = np.arange(1, N + 1)
    for idx, (case_name, data) in enumerate(all_results.items()):
        ax = axes[idx]
        ax2 = ax.twinx()

        # Power bars (Sigmoid)
        ax.bar(t_slots - 0.15, data["power"], 0.3, color='#2196F3',
               alpha=0.6, label='P(t) Sigmoid')
        ax.bar(t_slots + 0.15, data["power_log"], 0.3, color='#FF5722',
               alpha=0.6, label='P(t) Log')

        # Rate lines
        ax2.plot(t_slots, data["opt_rates"], '-o', color='#1565C0',
                 ms=3, lw=1.5, label='Rate (Sigmoid)')
        ax2.plot(t_slots, data["log_rates"], '-s', color='#BF360C',
                 ms=3, lw=1.5, label='Rate (Log)')
        ax2.axhline(y=3.0, color='#9C27B0', ls='--', lw=1, alpha=0.5)
        ax2.text(N + 0.5, 3.0, 'R_BL+R_EL', fontsize=7,
                 color='#9C27B0', va='center')

        ax.set_xlabel('Time Slot', fontsize=9)
        ax.set_ylabel('Power P(t) [W]', fontsize=9, color='#2196F3')
        ax2.set_ylabel('Rate R(t) [bps/Hz]', fontsize=9, color='#BF360C')
        ax.set_title(case_name, fontsize=10, fontweight='bold')
        ax.legend(fontsize=7, loc='upper left')
        ax2.legend(fontsize=7, loc='upper right')
        ax.grid(True, alpha=0.3)

    fig.suptitle('Power Allocation & Achievable Rate — 4 Configurations',
                 fontsize=13, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    pr_path = str(RESULTS_DIR / "power_rate_all_cases.png")
    fig.savefig(pr_path, dpi=150)
    print(f"  Saved: {pr_path}")

    # 10. Bảng tổng kết
    print("\n" + "=" * 85)
    print(f" {'Case':<22} {'Sigmoid':>10} {'LogQoE':>10} {'Straight':>10} {'Circle':>10}")
    print("-" * 85)
    for name, data in all_results.items():
        avg_o = np.mean(data["opt_rates"])
        avg_l = np.mean(data["log_rates"])
        avg_s = np.mean(data["straight_rates"])
        avg_c = np.mean(data["circle_rates"])
        print(f" {name:<22} {avg_o:>8.2f}   {avg_l:>8.2f}   {avg_s:>8.2f}   {avg_c:>8.2f}")
    print("=" * 85)
    print("\nDone! Run evaluator.py to measure PSNR.")

