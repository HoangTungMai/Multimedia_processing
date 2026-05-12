"""
UAV Trajectory & Power Optimization in Uplink CR-NOMA
Method: BCD + SCA
Model: 1 BS, 1 PU, 1 SU (UAV)

QoE = sum( w0/(1+exp(-a*(R-R_BL))) + w1/(1+exp(-a*(R-(R_BL+R_EL)))) )
"""
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize

# ===== System Parameters =====
q_A = np.array([0.0, 0.0])
q_B = np.array([200.0, 200.0])
w_BS = np.array([200.0, 0.0])
w_PU = np.array([100.0, 100.0])
H = 100.0  # UAV altitude (m)

N = 30; T = 30.0; dt = T/N
V_max = 15.0; D_max = V_max * dt
P_max = 0.5; P_pu = 0.3
beta0 = 1e-4; sigma2 = 1e-11
I_th = 5e-11; R_pu_min = 0.5

# QoE params
w0, w1, alpha_q = 0.6, 0.4, 5.0
R_BL, R_EL = 2.0, 3.0

# ===== Channel & Rate Functions =====
def h_uav(q): return beta0 / (np.sum((q - w_BS)**2) + H**2)
def g_pu(q):  return beta0 / (np.sum((q - w_PU)**2) + H**2)
h_pu_val = beta0 / np.sum((w_PU - w_BS)**2)

def rate_uav(p, q): return np.log2(1 + p * h_uav(q) / sigma2)
def rate_pu(p, q):   return np.log2(1 + P_pu * h_pu_val / (p * h_uav(q) + sigma2))

def qoe_slot(R):
    return w0/(1+np.exp(-alpha_q*(R - R_BL))) + w1/(1+np.exp(-alpha_q*(R - (R_BL+R_EL))))

# ===== BCD Step 1: Optimize Power (fixed trajectory) =====
def solve_power(traj):
    p = np.zeros(N)
    gamma_min = 2**R_pu_min - 1
    for n in range(N):
        p_interf = I_th / g_pu(traj[n])
        h_n = h_uav(traj[n])
        p_pu_qos = P_pu * h_pu_val / (gamma_min * h_n) - sigma2 / h_n
        p[n] = max(0, min(P_max, p_interf, max(0, p_pu_qos)))
    return p

# ===== BCD Step 2: Optimize Trajectory via SCA (fixed power) =====
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

# ===== Main BCD Loop =====
traj = np.array([q_A + (q_B-q_A)*(n+1)/(N+1) for n in range(N)])
p = np.ones(N) * 0.01
qoe_hist = []

print("="*55)
print(" UAV CR-NOMA Uplink: BCD + SCA Optimization")
print("="*55)
for it in range(8):
    p = solve_power(traj)
    traj = solve_trajectory(p, traj)
    qoe_val = sum(qoe_slot(rate_uav(p[n], traj[n])) for n in range(N))
    qoe_hist.append(qoe_val)
    print(f"  Iter {it+1}: QoE = {qoe_val:.4f}")

# ===== Compute Metrics =====
t_ax = np.arange(1, N+1)
rates = np.array([rate_uav(p[n], traj[n]) for n in range(N)])
pu_rates = np.array([rate_pu(p[n], traj[n]) for n in range(N)])
interf = np.array([p[n]*g_pu(traj[n]) for n in range(N)])
qoe_slots = np.array([qoe_slot(rates[n]) for n in range(N)])

# ===== Visualization =====
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("UAV CR-NOMA Uplink (BCD+SCA): 1BS, 1PU, 1SU", fontsize=14, fontweight='bold')

ax = axes[0,0]
ax.plot(traj[:,0], traj[:,1], 'b-o', ms=4, label='UAV Path')
ax.plot(*q_A, 'gs', ms=12, label='A'); ax.plot(*q_B, 'g^', ms=12, label='B')
ax.plot(*w_BS, 'kD', ms=10, label='BS'); ax.plot(*w_PU, 'r^', ms=12, label='PU')
ax.plot([q_A[0],q_B[0]], [q_A[1],q_B[1]], 'k--', alpha=0.3)
ax.add_patch(plt.Circle(w_PU, 30, color='r', fill=True, alpha=0.1))
ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)"); ax.set_title("Trajectory")
ax.legend(fontsize=8); ax.grid(True, alpha=0.3); ax.set_aspect('equal')

ax = axes[0,1]
ax2 = ax.twinx()
ax.bar(t_ax, p, color='steelblue', alpha=0.7, label='Power P(t)')
ax2.plot(t_ax, rates, 'r-s', ms=4, label='R_uav')
ax.set_xlabel("Time Slot"); ax.set_ylabel("Power (W)"); ax2.set_ylabel("Rate (bps/Hz)")
ax.set_title("Power & Rate"); ax.legend(loc='upper left', fontsize=8)
ax2.legend(loc='upper right', fontsize=8); ax.grid(True, alpha=0.3)

ax = axes[1,0]
ax.plot(t_ax, qoe_slots, 'g-o', ms=4, label='QoE/slot')
ax.axhline(w0+w1, color='g', ls='--', alpha=0.3, label=f'Max={w0+w1}')
ax.set_xlabel("Time Slot"); ax.set_ylabel("QoE"); ax.set_title("QoE (Double-Sigmoid)")
ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
ins = ax.inset_axes([0.55, 0.15, 0.4, 0.4])
ins.plot(range(1,9), qoe_hist, 'k-o', ms=3); ins.set_title("Convergence", fontsize=8)
ins.grid(True, alpha=0.3); ins.tick_params(labelsize=7)

ax = axes[1,1]
ax2 = ax.twinx()
ax.plot(t_ax, interf*1e10, 'm-o', ms=4, label='Interf (x1e-10)')
ax.axhline(I_th*1e10, color='r', ls='--', label=f'I_th')
ax2.plot(t_ax, pu_rates, 'c-s', ms=4, label='R_PU')
ax2.axhline(R_pu_min, color='b', ls='--', alpha=0.5, label=f'R_PU_min')
ax.set_xlabel("Time Slot"); ax.set_ylabel("Interference"); ax2.set_ylabel("PU Rate")
ax.set_title("Interference & PU Protection")
ax.legend(loc='upper left', fontsize=8); ax2.legend(loc='upper right', fontsize=8)
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('uav_cr_noma_results.png', dpi=150)
plt.show()
print("\nDone!")
