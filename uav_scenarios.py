"""
UAV CR-NOMA: 4 Challenging Scenarios (including Multi-PU)
A: PU blocks direct path
B: PU near BS
C: Tight constraints
D: 3 PUs forming a barrier
"""
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize

# ===== Common Functions =====
def h_gain(p1, p2, H):
    return 1e-4 / (np.sum((p1-p2)**2) + H**2)

def rate(p, q, bs, H):
    return np.log2(1 + p * h_gain(q, bs, H) / 1e-11)

def qoe_slot(R, R_BL=2.0, R_EL=3.0):
    return 0.6/(1+np.exp(-5*(R-R_BL))) + 0.4/(1+np.exp(-5*(R-(R_BL+R_EL))))

# --- Single-PU scenario runner (A, B, C) ---
def run_single_pu(q_A, q_B, w_BS, w_PU, H, N, T, V_max, P_max, P_pu, I_th, R_pu_min):
    dt = T/N; D_max = V_max*dt; sigma2=1e-11; beta0=1e-4
    h_pu_bs = beta0 / np.sum((w_PU - w_BS)**2)

    def solve_p(traj):
        p = np.zeros(N); gm = 2**R_pu_min - 1
        for n in range(N):
            g = h_gain(traj[n], w_PU, H)
            h_n = h_gain(traj[n], w_BS, H)
            p[n] = max(0, min(P_max, I_th/g, max(0, P_pu*h_pu_bs/(gm*h_n)-sigma2/h_n)))
        return p

    def solve_traj(p, tk):
        x0 = tk.flatten()
        def obj(x):
            t = x.reshape((N,2)); v = 0
            for n in range(N):
                dk2 = np.sum((tk[n]-w_BS)**2)+H**2
                A = p[n]*beta0/sigma2
                Rk = np.log2(1+A/(dk2+1e-9))
                dR = -A*np.log2(np.e)/(dk2*(dk2+A)+1e-12)
                d2 = np.sum((t[n]-w_BS)**2)+H**2
                v -= qoe_slot(Rk + dR*(d2-dk2))
            return v
        def cons(x):
            t = x.reshape((N,2)); c = []
            c.append(D_max**2 - np.sum((t[0]-q_A)**2))
            for n in range(N-1): c.append(D_max**2 - np.sum((t[n+1]-t[n])**2))
            c.append(D_max**2 - np.sum((q_B-t[-1])**2))
            for n in range(N):
                if p[n]<1e-15: c.append(1.0); continue
                Ds = p[n]*beta0/I_th - H**2
                if Ds<0: c.append(1.0); continue
                qk = tk[n]-w_PU
                c.append(np.sum(qk**2)+2*np.dot(qk,t[n]-tk[n])-Ds)
            return np.array(c)
        res = minimize(obj, x0, method='SLSQP',
                       constraints={'type':'ineq','fun':cons}, options={'maxiter':80})
        return res.x.reshape((N,2))

    traj = np.array([q_A+(q_B-q_A)*(n+1)/(N+1) for n in range(N)])
    p = np.ones(N)*0.01; qoe_hist = []
    for _ in range(8):
        p = solve_p(traj); traj = solve_traj(p, traj)
        qoe_hist.append(sum(qoe_slot(rate(p[n],traj[n],w_BS,H)) for n in range(N)))
    rates_v = np.array([rate(p[n],traj[n],w_BS,H) for n in range(N)])
    qoe_s = np.array([qoe_slot(rates_v[n]) for n in range(N)])
    return traj, p, rates_v, qoe_s, qoe_hist, [w_PU]

# --- Multi-PU scenario runner (D) ---
def run_multi_pu(q_A, q_B, w_BS, PU_list, H, N, T, V_max, P_max, P_pu, I_th, R_pu_min):
    dt = T/N; D_max = V_max*dt; sigma2=1e-11; beta0=1e-4
    K = len(PU_list)

    def solve_p(traj):
        p = np.zeros(N)
        for n in range(N):
            p_bound = P_max
            for k in range(K):
                g_k = h_gain(traj[n], PU_list[k], H)
                p_bound = min(p_bound, I_th / g_k)
            p[n] = max(0, p_bound)
        return p

    def solve_traj(p, tk):
        x0 = tk.flatten()
        def obj(x):
            t = x.reshape((N,2)); v = 0
            for n in range(N):
                dk2 = np.sum((tk[n]-w_BS)**2)+H**2
                A = p[n]*beta0/sigma2
                Rk = np.log2(1+A/(dk2+1e-9))
                dR = -A*np.log2(np.e)/(dk2*(dk2+A)+1e-12)
                d2 = np.sum((t[n]-w_BS)**2)+H**2
                v -= qoe_slot(Rk + dR*(d2-dk2))
            return v
        def cons(x):
            t = x.reshape((N,2)); c = []
            c.append(D_max**2 - np.sum((t[0]-q_A)**2))
            for n in range(N-1): c.append(D_max**2 - np.sum((t[n+1]-t[n])**2))
            c.append(D_max**2 - np.sum((q_B-t[-1])**2))
            # Interference constraint for EACH PU
            for k in range(K):
                for n in range(N):
                    if p[n]<1e-15: c.append(1.0); continue
                    Ds = p[n]*beta0/I_th - H**2
                    if Ds<0: c.append(1.0); continue
                    qk = tk[n]-PU_list[k]
                    c.append(np.sum(qk**2)+2*np.dot(qk,t[n]-tk[n])-Ds)
            return np.array(c)
        res = minimize(obj, x0, method='SLSQP',
                       constraints={'type':'ineq','fun':cons}, options={'maxiter':80})
        return res.x.reshape((N,2))

    traj = np.array([q_A+(q_B-q_A)*(n+1)/(N+1) for n in range(N)])
    p = np.ones(N)*0.01; qoe_hist = []
    for _ in range(8):
        p = solve_p(traj); traj = solve_traj(p, traj)
        qoe_hist.append(sum(qoe_slot(rate(p[n],traj[n],w_BS,H)) for n in range(N)))
    rates_v = np.array([rate(p[n],traj[n],w_BS,H) for n in range(N)])
    qoe_s = np.array([qoe_slot(rates_v[n]) for n in range(N)])
    return traj, p, rates_v, qoe_s, qoe_hist, PU_list

# ===== Define 4 Scenarios =====
results = {}

print("="*55+"\n  A: PU chan duong bay\n"+"="*55)
results["A: PU chặn đường"] = run_single_pu(
    np.array([0.,0.]), np.array([200.,200.]),
    np.array([100.,0.]), np.array([100.,100.]),
    100., 30, 30., 15., 0.5, 0.3, 5e-11, 0.5)

print("="*55+"\n  B: PU sat BS\n"+"="*55)
results["B: PU sát BS"] = run_single_pu(
    np.array([0.,0.]), np.array([200.,200.]),
    np.array([200.,0.]), np.array([180.,20.]),
    100., 30, 30., 15., 0.5, 0.3, 3e-11, 0.8)

print("="*55+"\n  C: Rang buoc chat\n"+"="*55)
results["C: Ràng buộc chặt"] = run_single_pu(
    np.array([0.,0.]), np.array([200.,200.]),
    np.array([200.,0.]), np.array([100.,50.]),
    100., 30, 30., 10., 0.3, 0.3, 1e-11, 1.0)

print("="*55+"\n  D: 3 PU barrier\n"+"="*55)
results["D: 3 PU barrier"] = run_multi_pu(
    q_A=np.array([0.,0.]), q_B=np.array([200.,200.]),
    w_BS=np.array([200.,0.]),
    PU_list=[np.array([60.,80.]), np.array([100.,100.]), np.array([140.,120.])],
    H=100., N=30, T=30., V_max=15., P_max=0.5, P_pu=0.3, I_th=5e-11, R_pu_min=0.5)

for name, (_, _, _, _, hist, _) in results.items():
    print(f"  {name}: Final QoE = {hist[-1]:.4f}")

# ===== Visualization: 4 rows x 4 cols =====
I_th_list = [5e-11, 3e-11, 1e-11, 5e-11]  # I_th for each scenario
fig, axes = plt.subplots(4, 4, figsize=(20, 20))
fig.suptitle("UAV CR-NOMA: 4 Scenarios (incl. Multi-PU Barrier)", fontsize=16, fontweight='bold')
colors = ['#2196F3', '#FF5722', '#4CAF50', '#9C27B0']
q_A = np.array([0.,0.]); q_B = np.array([200.,200.])
bs_locs = [np.array([100.,0.]), np.array([200.,0.]), np.array([200.,0.]), np.array([200.,0.])]
H = 100.0

for row, (name, (traj, p, rates_v, qoe_s, qoe_hist, pu_list)) in enumerate(results.items()):
    t_ax = np.arange(1, 31); c = colors[row]
    I_th_cur = I_th_list[row]

    # Col 1: Trajectory
    ax = axes[row, 0]
    ax.plot(traj[:,0], traj[:,1], '-o', color=c, ms=3, label='UAV')
    ax.plot(*q_A, 'gs', ms=10); ax.plot(*q_B, 'g^', ms=10)
    ax.plot(*bs_locs[row], 'kD', ms=8, label='BS')
    ax.plot([q_A[0],q_B[0]], [q_A[1],q_B[1]], 'k--', alpha=0.2)
    for pu in pu_list:
        ax.plot(*pu, 'r^', ms=10)
        ax.add_patch(plt.Circle(pu, 25, color='r', fill=True, alpha=0.1))
    ax.set_title(name, fontweight='bold'); ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7); ax.set_aspect('equal')

    # Col 2: Power & Rate
    ax = axes[row, 1]; ax2 = ax.twinx()
    ax.bar(t_ax, p, color=c, alpha=0.5, label='P(t)')
    ax2.plot(t_ax, rates_v, 'r-', ms=3, label='Rate')
    ax.set_title("Power & Rate"); ax.grid(True, alpha=0.3)
    ax.legend(loc='upper left', fontsize=7); ax2.legend(loc='upper right', fontsize=7)

    # Col 3: QoE
    ax = axes[row, 2]
    ax.plot(t_ax, qoe_s, '-o', color='green', ms=3)
    ax.axhline(1.0, color='g', ls='--', alpha=0.3)
    ax.set_title("QoE per Slot"); ax.set_ylim(0, 1.1); ax.grid(True, alpha=0.3)

    # Col 4: Interference at each PU + threshold
    ax = axes[row, 3]
    pu_colors = ['#E91E63', '#FF9800', '#795548']
    for k, pu in enumerate(pu_list):
        interf_k = np.array([p[n] * h_gain(traj[n], pu, H) for n in range(30)])
        label = f'PU{k+1}' if len(pu_list) > 1 else 'Interf at PU'
        ax.plot(t_ax, interf_k * 1e10, '-o', color=pu_colors[k % 3], ms=3, label=label)
    ax.axhline(I_th_cur * 1e10, color='red', ls='--', lw=2, label=f'I_th')
    ax.set_title("Interference (×1e-10)"); ax.grid(True, alpha=0.3)
    ax.legend(fontsize=7); ax.set_xlabel("Time Slot")

plt.tight_layout()
plt.savefig('uav_scenarios_comparison.png', dpi=150)
plt.show()
print("\nAll 4 scenarios done!")
