"""
================================================================================
H.264 Adaptive Encoder — UAV CR-NOMA Video Transmission
================================================================================
Nén video foreman_cif.yuv bằng FFmpeg (libx264) với QP thích nghi theo
Rate R(t) từ thuật toán tối ưu BCD+SCA trong uav_simulation.py.

Pipeline:
  uav_simulation.py → Rate R(t) → rate_to_qp() → FFmpeg encode → .264 bitstream

Kịch bản đối chứng:
  - Optimized (BCD+SCA): Quỹ đạo + công suất tối ưu
  - Straight Line:       Bay thẳng A→B, công suất an toàn
  - Circle:              Bay vòng tròn né PU, công suất an toàn
================================================================================
"""

import os
import subprocess
import numpy as np
import json
import imageio_ffmpeg
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "results" / "bitstreams"
YUV_PATH = BASE_DIR / "foreman_cif.yuv"


class MultiScenarioEncoder:
    def __init__(self, yuv_path, width=352, height=288):
        self.yuv_path = str(yuv_path)
        self.width = width
        self.height = height
        self.frame_size = int(width * height * 1.5)
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    def rate_to_qp(self, rate):
        """
        Ánh xạ Rate (bps/Hz) sang QP.
        Rate ~2.0 → QP=32 (kênh xấu, nén mạnh)
        Rate ~4.0 → QP=10 (kênh tốt, nén nhẹ, chất lượng cao)
        """
        qp = 32 - (rate - 2.0) * (22 / 2.0)
        return int(np.clip(qp, 10, 45))

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

    def run_scenario(self, scenario_name, rates, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"\n  [{scenario_name}]")
        total_size = 0
        for i, r in enumerate(rates):
            qp = self.rate_to_qp(r)
            output_path = os.path.join(output_dir, f"slot_{i+1:03d}.264")
            frames_data = self.get_segment_frames(i * 10, 10)
            self.encode_gop(frames_data, output_path, qp)
            size = os.path.getsize(output_path) / 1024
            total_size += size
            if i % 10 == 0 or i == len(rates) - 1:
                print(f"    Slot {i+1:2d}/30: Rate={r:.2f} bps/Hz -> QP={qp:2d} | {size:.1f} KB")
        print(f"    Total size: {total_size:.1f} KB")


# ============================================================
# Hàm tạo dữ liệu baseline (thay cho file run_baselines.py)
# ============================================================

def generate_baselines():
    """Tạo dữ liệu Rate cho các kịch bản đối chứng"""
    q_A = np.array([0.0, 0.0])
    q_B = np.array([200.0, 200.0])
    w_BS = np.array([200.0, 0.0])
    w_PU = np.array([100.0, 100.0])
    H = 100.0; N = 30
    beta0 = 1e-4; sigma2 = 1e-11
    P_safe = 0.005  # Công suất an toàn (5mW) để không nhiễu PU

    def h_uav(q): return beta0 / (np.sum((q - w_BS)**2) + H**2)
    def rate_uav(p, q): return np.log2(1 + p * h_uav(q) / sigma2)

    # Straight line: A → B
    traj_straight = np.array([q_A + (q_B-q_A)*(n+1)/(N+1) for n in range(N)])
    rates_straight = [rate_uav(P_safe, q) for q in traj_straight]

    # Circle: Vòng tròn quanh PU (né PU, xa BS)
    r_avoid = 120.0
    angles = np.linspace(0, np.pi, N)
    traj_circle = np.array([w_PU + np.array([r_avoid*np.cos(a), r_avoid*np.sin(a)]) for a in angles])
    rates_circle = [rate_uav(P_safe, q) for q in traj_circle]

    return {
        "straight": rates_straight,
        "circle": rates_circle
    }


# ============================================================
# Hàm chạy simulation gốc (thay cho file run_orig_sim.py)
# ============================================================

def run_original_simulation():
    """Chạy thuật toán BCD+SCA từ uav_simulation.py và trả về rates"""
    from scipy.optimize import minimize

    q_A = np.array([0.0, 0.0])
    q_B = np.array([200.0, 200.0])
    w_BS = np.array([200.0, 0.0])
    w_PU = np.array([100.0, 100.0])
    H = 100.0
    N = 30; T = 30.0; dt = T/N
    V_max = 15.0; D_max = V_max * dt
    P_max = 0.5; P_pu = 0.3
    beta0 = 1e-4; sigma2 = 1e-11
    I_th = 5e-11; R_pu_min = 0.5
    w0, w1, alpha_q = 0.6, 0.4, 5.0
    R_BL, R_EL = 2.0, 3.0

    def h_uav(q): return beta0 / (np.sum((q - w_BS)**2) + H**2)
    def g_pu(q):  return beta0 / (np.sum((q - w_PU)**2) + H**2)
    h_pu_val = beta0 / np.sum((w_PU - w_BS)**2)
    def rate_uav(p, q): return np.log2(1 + p * h_uav(q) / sigma2)
    def qoe_slot(R):
        return w0/(1+np.exp(-alpha_q*(R - R_BL))) + w1/(1+np.exp(-alpha_q*(R - (R_BL+R_EL))))

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

    print("  Running BCD+SCA optimization (8 iterations)...")
    for it in range(8):
        p = solve_power(traj)
        traj = solve_trajectory(p, traj)
        qoe_val = sum(qoe_slot(rate_uav(p[n], traj[n])) for n in range(N))
        print(f"    Iter {it+1}: QoE = {qoe_val:.4f}")

    rates = [rate_uav(p[n], traj[n]) for n in range(N)]
    return rates


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print(" UAV CR-NOMA H.264 Adaptive Encoder")
    print("=" * 60)

    encoder = MultiScenarioEncoder(YUV_PATH)

    # Step 1: Chạy simulation gốc
    print("\n[Step 1] Running Optimization...")
    opt_rates = run_original_simulation()

    # Step 2: Tạo baseline
    print("\n[Step 2] Generating Baselines...")
    baselines = generate_baselines()

    # Step 3: Encode tất cả
    print("\n[Step 3] Encoding Video...")
    encoder.run_scenario("Optimized (BCD+SCA)",
                         opt_rates, str(DATA_DIR / "Optimized"))
    encoder.run_scenario("Straight Line",
                         baselines["straight"], str(DATA_DIR / "Straight"))
    encoder.run_scenario("Circle",
                         baselines["circle"], str(DATA_DIR / "Circle"))

    print("\n" + "=" * 60)
    print(" All scenarios encoded successfully!")
    print("=" * 60)
