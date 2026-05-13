# BÁO CÁO TỔNG HỢP & PHẢN BIỆN
## Đề tài: Tối Ưu Truyền Video UAV Trên Mạng CR-NOMA

---

# PHẦN I: TỔNG KẾT DỰ ÁN

## I. Bài Toán Đặt Ra

**Bối cảnh:** Một UAV bay từ điểm A đến điểm B, vừa bay vừa quay video và truyền về trạm gốc BS (Base Station). Trên mặt đất có PU (Primary User) đang sử dụng cùng tần số → UAV phải **chia sẻ phổ** mà không gây nhiễu quá ngưỡng cho PU.

**Câu hỏi nghiên cứu:** Làm sao để UAV truyền video về BS với **chất lượng cao nhất có thể**, trong khi phải tuân thủ:

- Giới hạn tốc độ bay ($V_{max}$ = 15 m/s)
- Giới hạn công suất phát ($P_{max}$ = 0.5 W)
- Ràng buộc nhiễu CR ($I_{th}$ = 5×10⁻¹¹ W, $R_{PU,min}$ = 0.5 bps/Hz)

---

## II. Mô Hình Hệ Thống

```
Không gian 2D (200m × 200m)

  🟢 A(0,0) ──────────────── 🟢 B(200,200)
              🛩️ UAV (H=100m)
                  │ truyền video
                  ▼
              🏢 BS (Base Station)
                  ·
                  · (nhiễu ≤ I_th)
                  ·
              📱 PU (Primary User)
```

### Tham số hệ thống

| Tham số | Ký hiệu | Giá trị | Ý nghĩa |
|---|---|---|---|
| Độ cao bay | $H$ | 100 m | Cố định (LoS channel) |
| Số time slot | $N$ | 30 | Mỗi slot = 1 giây |
| Tổng thời gian | $T$ | 30 s | Thời gian bay từ A→B |
| Tốc độ tối đa | $V_{max}$ | 15 m/s | Ràng buộc cơ học |
| Công suất tối đa | $P_{max}$ | 0.5 W | Ràng buộc năng lượng |
| Ngưỡng nhiễu CR | $I_{th}$ | 5×10⁻¹¹ W | Bảo vệ PU |
| Path-loss factor | $\beta_0$ | 10⁻⁴ | Kênh LoS |
| Noise power | $\sigma^2$ | 10⁻¹¹ W | Nhiễu Gauss |

---

## III. Quy Trình Thực Hiện (Pipeline)

```
┌─────────────────────────────┐     ┌──────────────────────────────┐
│      Bước 1: encoder.py     │     │     Bước 2: evaluator.py     │
│                             │     │                              │
│  BCD+SCA                    │     │  H.264 Decoder               │
│  Tối ưu quỹ đạo             │     │       ↓                      │
│       ↓                     │     │  So sánh với video gốc       │
│  Rate R(t) — 30 giá trị     │ ──► │       ↓                      │
│       ↓                     │     │  PSNR (dB) mỗi frame         │
│  H.264 Encoder (FFmpeg)     │     │       ↓                      │
│       ↓                     │     │  Biểu đồ so sánh             │
│  .264 bitstream (30 GOP)    │     │                              │
└─────────────────────────────┘     └──────────────────────────────┘
```

---

## IV. Thuật Toán BCD+SCA

### 4.1. Block Coordinate Descent

Chia bài toán tối ưu đồng thời (quỹ đạo + công suất) thành 2 bài toán con, giải luân phiên:

```
Khởi tạo: quỹ đạo = đường thẳng A→B, công suất = 0.01 W

Lặp 8 vòng:
  ① Cố định quỹ đạo q(t) → Giải tối ưu công suất P(t)
     P(t) = min(P_max, I_th / g_PU(q(t)), ...)

  ② Cố định công suất P(t) → Giải tối ưu quỹ đạo q(t) bằng SCA
     - Xấp xỉ hàm Rate bằng Taylor bậc 1
     - Giải bài toán SLSQP với ràng buộc tốc độ bay + nhiễu

  → R(t) = log₂(1 + P(t)·h(q(t)) / σ²)
  → QoE  = Σ qoe_slot(R(t))
```

### 4.2. Hàm mục tiêu QoE

**Sigmoid QoE** (cho SVC):
$$QoE_{sig}(R) = \frac{0.6}{1+e^{-5(R-2.0)}} + \frac{0.4}{1+e^{-5(R-5.0)}}$$

**Logarithmic QoE** (cho Adaptive QP):
$$QoE_{log}(R) = \log_2(1 + R)$$

### 4.3. Đầu ra của BCD+SCA

Với mỗi cấu hình PU/BS, thuật toán cho ra:

- `rates[30]` — Tốc độ truyền tại mỗi slot (bps/Hz)
- `trajectory[30×2]` — Tọa độ UAV tại mỗi slot
- `power[30]` — Công suất phát tại mỗi slot

---

## V. Phương Pháp Mã Hóa Video

### 5.1. Video đầu vào

`foreman_cif.yuv` — CIF 352×288, 300 frames, YUV420, chia thành **30 GOP × 10 frames/GOP**.

### 5.2. Các phương pháp so sánh

| Phương pháp | Quỹ đạo | Cách chọn QP |
|---|---|---|
| **Optimized** | BCD+SCA (Sigmoid) | QP = 32 − (R−2.0)×11, liên tục |
| **Opt_LogQoE** | BCD+SCA (Log) | QP = 32 − (R−2.0)×11, liên tục |
| **Straight** | Đường thẳng A→B | QP tính theo Rate thấp |
| **Circle** | Nửa vòng tròn | QP tính theo Rate trung bình |
| **SVC** | BCD+SCA (Sigmoid) | BL: QP=35 cố định, EL: QP=15 cố định |

### 5.3. Ánh xạ Cross-layer (Adaptive QP)

```
Rate R(t) (bps/Hz)  →  QP  →  Chất lượng
    2.0             →  32  →  Mờ (vừa đủ xem)
    2.5             →  27  →  Trung bình
    3.0             →  21  →  Khá tốt
    3.5             →  16  →  Rất nét
    4.0             →  10  →  Gần lossless
```

---

## VI. Kết Quả PSNR Trung Bình (dB)

| Case | Opt (Sigmoid) | Opt (LogQoE) | SVC | Circle | Straight |
|---|---|---|---|---|---|
| Case1 Default | 37.80 | **37.97** | 35.92 | 31.23 | 28.76 |
| Case2 PU Blocking | 37.60 | **37.97** | 35.92 | 31.23 | 28.76 |
| Case3 BS Far | **33.59** | **33.59** | 27.54 | 29.44 | 27.16 |
| Case4 Opposite | 40.18 | **41.16** | 38.95 | 26.87 | 29.97 |
| Case5 PU Near Start | 37.80 | **39.04** | 33.44 | 31.23 | 28.76 |

---

## VII. Kết Luận Chính

> **① Tối ưu quỹ đạo là yếu tố then chốt:** BCD+SCA mang lại **+6 đến +13 dB** so với các baseline đơn giản (Straight, Circle).

> **② Cross-layer Adaptive QP vượt trội SVC:** Trong mọi kịch bản, Adaptive QP đều ≥ SVC, đặc biệt ở kênh xấu (Case 3: vượt **+6.05 dB**) nhờ tận dụng liên tục từng bps/Hz.

> **③ Log QoE tối ưu hơn Sigmoid QoE:** Khi ghép đúng hàm mục tiêu với phương pháp mã hóa, PSNR tăng thêm **+0.2 đến +1.2 dB** (đặc biệt ở Case 4 và 5).

---

## VIII. Cấu Trúc File & Cách Chạy

```
📁 XLA và truyền thông đa phương tiện/
├── 📄 encoder.py          ← BCD+SCA + H.264 Encoder (Bước 1)
├── 📄 evaluator.py        ← PSNR Evaluator + Biểu đồ (Bước 2)
├── 📄 uav_scenarios.py    ← 4 kịch bản nâng cao (Multi-PU)
├── 🎬 foreman_cif.yuv     ← Video gốc (không push lên Git, 43.5 MB)
└── 📁 results/
    ├── 📁 bitstreams/
    ├── 🖼️ trajectories_all_cases.png
    ├── 🖼️ comprehensive_comparison.png
    ├── 🖼️ psnr_all_cases.png
    ├── 🖼️ psnr_summary_bar.png
    ├── 🖼️ svc_optimal_analysis.png
    └── 🖼️ svc_vs_adaptive_detail.png
```

```bash
# Bước 1: Tối ưu + Mã hóa (~2 phút)
python encoder.py

# Bước 2: Đánh giá + Vẽ biểu đồ (~20 giây)
python evaluator.py
```

> ⚠️ Cần có file `foreman_cif.yuv` trong thư mục gốc trước khi chạy.

---
---

# PHẦN II: REVIEW & PHẢN BIỆN HỌC THUẬT

## I. Điểm Mạnh

| # | Điểm mạnh | Nhận xét |
|---|---|---|
| ✅ | **Bài toán thực tế** | Kết hợp 3 lớp kỹ thuật (quỹ đạo, CR, video) trong một hệ thống thống nhất — liên ngành, có ý nghĩa |
| ✅ | **Pipeline rõ ràng** | Tách bạch encoder/evaluator, pipeline tái hiện được và dễ kiểm tra từng bước |
| ✅ | **Baseline đa dạng** | 5 phương pháp × 5 kịch bản cho kết quả định lượng thuyết phục |
| ✅ | **Kết quả định lượng** | PSNR cụ thể, chênh lệch lớn (+6 đến +13 dB) giữa optimized và baseline |

---

## II. Điểm Yếu — Phản Biện Học Thuật

### W1 — Thiếu ràng buộc NOMA thực sự ⚠️ (Nghiêm trọng)

**Vấn đề:**
Tên đề tài có "NOMA" nhưng trong toàn bộ mô hình không thấy:
- SIC (Successive Interference Cancellation) tại bộ thu
- Power allocation ratio giữa các user NOMA
- Ít nhất 2 user chia sẻ cùng tài nguyên theo power-domain multiplexing

Mô hình hiện tại chỉ có **1 UAV + 1 BS** với ràng buộc CR của PU → đây là **CR thuần túy (underlay spectrum sharing)**, không phải CR-NOMA.

**Khuyến nghị:**
> Làm rõ cơ chế NOMA hoặc thêm mô hình multi-user với SIC tại BS. Nếu không, cân nhắc đổi tên thành *"CR-based UAV Video Transmission"* để tránh bị phản biện tại hội đồng.

---

### W2 — Hàm QoE chưa có cơ sở chuẩn hóa ⚠️

**Vấn đề:**
Các hệ số trong Sigmoid QoE được thiết kế tùy chỉnh:

$$QoE_{sig}(R) = \frac{0.6}{1+e^{-5(R-2.0)}} + \frac{0.4}{1+e^{-5(R-5.0)}}$$

Không có trích dẫn từ chuẩn **ITU-T P.1203**, **VMAF** hay bất kỳ nghiên cứu nào. Thiếu **ablation study** về độ nhạy của kết quả với các hệ số (0.6, 0.4, 2.0, 5.0).

**Khuyến nghị:**
> Trích dẫn tài liệu nguồn gốc các hệ số, hoặc thực hiện sensitivity analysis: nếu đổi 0.6/0.4 thành 0.5/0.5, hoặc đổi ngưỡng từ 2.0 thành 1.5, kết quả có thay đổi đáng kể không?

---

### W3 — Mô hình kênh đơn giản hóa quá mức ⚠️

**Vấn đề:**
Kênh LoS thuần với path-loss $\beta_0/d^2$ bỏ qua:
- **Shadowing** và **multipath fading**
- **Doppler effect**: UAV ở 15 m/s tạo Doppler shift ~280 Hz ở 5.8 GHz
- **Rician K-factor** thay đổi theo góc ngẩng trong kênh A2G thực tế

Kết quả PSNR hiện tại là **upper bound lý thuyết**, không phải performance trong điều kiện thực.

**Khuyến nghị:**
> Thêm mô phỏng Monte Carlo với Rician fading. Ít nhất cần nêu rõ đây là giới hạn (limitation) trong phần thảo luận.

---

### W4 — Đánh giá chỉ dùng PSNR là không đủ ⚠️

**Vấn đề:**
PSNR có tương quan yếu với chất lượng cảm nhận (MOS) ở vùng PSNR cao (>35 dB). Mâu thuẫn lớn: đề tài tên là **"QoE optimization"** nhưng đánh giá bằng metric kỹ thuật thuần túy.

Thiếu:
- **SSIM** (Structural Similarity Index)
- **MS-SSIM** hoặc **VMAF** — metric ITU khuyến nghị cho video QoE

Ở vùng 37–41 dB, sự khác biệt 1–2 dB PSNR gần như **không nhận thấy được bằng mắt người**.

**Khuyến nghị:**
> Thêm SSIM vào `evaluator.py` — chỉ cần ~3 dòng code:
> ```python
> from skimage.metrics import structural_similarity as ssim
> score = ssim(frame_orig, frame_decoded, channel_axis=2)
> ```

---

### W5 — BCD hội tụ chưa được chứng minh ⚠️

**Vấn đề:**
8 vòng lặp BCD là con số cố định không có lý giải. Thiếu:
- **Convergence curve** (QoE theo số vòng lặp)
- Chứng minh **KKT conditions** hay **local optimality** của SCA solution

**Khuyến nghị:**
> Vẽ đồ thị QoE theo vòng lặp (1→8). Nếu QoE plateau sau vòng 5–6, con số 8 vòng là đủ và có căn cứ thực nghiệm.

---

## III. Câu Hỏi Hội Đồng Có Thể Hỏi

| Câu hỏi | Gợi ý trả lời |
|---|---|
| "Tại sao gọi là NOMA nếu không có SIC?" | Giải thích hoặc thừa nhận đây là CR; bổ sung multi-user extension vào hướng phát triển |
| "Nếu kênh có Rician fading, PSNR có giảm mạnh không?" | Đây là giới hạn nghiên cứu; kết quả là upper bound — đề xuất Monte Carlo |
| "Tại sao chọn 8 vòng lặp BCD?" | Trình bày convergence curve; nếu chưa có thì trả lời là giá trị kinh nghiệm, cần thực nghiệm thêm |
| "PSNR 37 dB vs 38 dB — người dùng nhận thấy không?" | Thừa nhận hạn chế PSNR; đề xuất SSIM/VMAF trong nghiên cứu tiếp theo |
| "Các hệ số 0.6/0.4 trong Sigmoid QoE từ đâu?" | Trích dẫn tài liệu hoặc giải thích là thiết kế thực nghiệm |

---

## IV. Khuyến Nghị Ưu Tiên

| Ưu tiên | Hành động | Effort | Giải quyết |
|---|---|---|---|
| 🔴 #1 | Thêm SSIM vào `evaluator.py` | ~30 phút | W4 |
| 🔴 #2 | Vẽ convergence curve BCD | ~1 giờ | W5 |
| 🟡 #3 | Làm rõ NOMA hoặc đổi tên đề tài | ~2 giờ | W1 |
| 🟡 #4 | Bổ sung tài liệu tham khảo cho hàm QoE | ~1 giờ | W2 |
| 🟢 #5 | Thêm Rician fading simulation | ~1 ngày | W3 |

---

*Báo cáo tổng hợp từ `project_summary_final.md` — Tối Ưu Truyền Video UAV Trên Mạng CR-NOMA*
