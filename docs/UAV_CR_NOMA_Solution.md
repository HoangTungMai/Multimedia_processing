# Bài toán: Tối ưu Lập lịch Bay và Công suất UAV (Mô hình 1 BS, 1 PU, 1 SU)

Để đơn giản hóa và tập trung vào bản chất của bài toán, tôi đã thiết kế lại mô hình với 3 thành phần cốt lõi:

## 1. Các thành phần hệ thống
- **1 Base Station (BS)**: Trạm gốc mặt đất đóng vai trò là bộ thu tín hiệu từ UAV.
- **1 Primary User (PU)**: Người dùng ưu tiên, có quyền sử dụng phổ tần cao nhất. UAV phải đảm bảo nhiễu gây ra tại PU luôn dưới ngưỡng cho phép.
- **1 Secondary User (UAV)**: Trạm phát di động cần bay từ A đến B.

## 2. Thiết kế Phương trình QoE
QoE của UAV (SU) phụ thuộc vào sự cân bằng giữa quỹ đạo và công suất:
$$\max_{\{q, P\}} \sum_{t=1}^{N} \text{Rate}(t) = \sum_{t=1}^{N} \log_2 \left( 1 + \frac{P(t) \cdot \text{Gain}(q(t), w_{BS})}{\text{Noise}} \right)$$

- **Chất lượng tín hiệu**: Khi UAV ở xa BS hoặc phát công suất thấp, tín hiệu sẽ chập chờn. Do đó, UAV có xu hướng bay gần BS.
- **Ràng buộc nhiễu**: Khi UAV bay gần PU, nó buộc phải giảm công suất $P(t)$ để không vi phạm $I_{PU} \le I_{th}$. Điều này làm giảm QoE.

## 3. Thuật toán BCD + SCA
Thuật toán lập lịch sẽ tìm ra điểm cân bằng bằng cách:
1.  **BCD (Block Coordinate Descent)**: Tối ưu luân phiên Công suất (Power) và Quỹ đạo (Trajectory).
2.  **SCA (Successive Convex Approximation)**: Giải quyết tính phi lồi của quỹ đạo bay. Tại mỗi bước lặp, chúng ta tuyến tính hóa hàm log và các ràng buộc khoảng cách để tìm ra hướng di chuyển tốt nhất cho UAV.

---

## 4. Mô phỏng (Simplified Model Visualization)

Dưới đây là hình ảnh minh họa bài toán lập lịch tối ưu. UAV (SU) điều chỉnh quỹ đạo để vừa "áp sát" BS (để tăng chất lượng tín hiệu) vừa "né" vùng ảnh hưởng của PU (để có thể phát công suất cao hơn).

![Mô phỏng 3 Nút](/C:/Users/pikac/.gemini/antigravity/brain/996513e9-b4a7-4ad7-a5a3-7b01fe3a347a/uav_simplified_cr_noma_model_1778440815003.png)

---

## 5. Mã nguồn Python (Cập nhật)

Mã nguồn đã được tối giản hóa cho mô hình 1 BS, 1 PU, 1 SU.

[uav_simulation.py](file:///d:/XLA%20v%C3%A0%20try%E1%BB%81n%20th%C3%B4ng%20%C4%91a%20ph%C6%B0%C6%A1ng%20ti%E1%BB%87n/uav_simulation.py)

```python
# Các biến chính
BS_LOC = np.array([100, 0])   # Vị trí Trạm Gốc
PU_LOC = np.array([50, 50])   # Vị trí Người dùng ưu tiên
START = np.array([0, 0])      # Điểm bắt đầu của UAV
END = np.array([100, 100])    # Điểm kết thúc của UAV
```

> [!TIP]
> Kết quả mô phỏng cho thấy UAV sẽ bay theo một đường cong "lượn" về phía BS nhưng vẫn duy trì một khoảng cách an toàn với PU để đạt được QoE cao nhất.
