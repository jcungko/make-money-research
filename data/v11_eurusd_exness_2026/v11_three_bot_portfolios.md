# V11 EURUSD — Lựa chọn 3 tổ hợp, mỗi tổ hợp gồm 3 bot

Dữ liệu: 100 phương pháp đã sàng lọc từ Jan–Oct 2026 trên nến M5 Exness theo Bid/Ask; log chi tiết Jan–Oct và tái kiểm thử tháng 11 đến 10/11 (7 ngày giao dịch đủ dữ liệu, mẫu 11/11 UTC chưa hoàn tất). **62/100** phương pháp có pip ròng dương trong tháng 11; kiểm tra toàn bộ **37.820** tổ hợp `C(62,3)=37.820`.

### Định nghĩa phép đo

- **Ngày cả 3 cùng thua:** cả ba chiến lược cùng có pip < 0 trên ngày UTC *mở lệnh*. Ngày 0 nếu một bot không vào lệnh. Kiểm tra trên 216 ngày UTC hợp lệ Jan–Oct + 7 ngày UTC đủ dữ liệu 02–10/11, tổng 223 ngày giao dịch.
- **Ngày từ 2 bot cùng thua:** ít nhất hai phương pháp có pip < 0 trong cùng ngày UTC.
- **Tương quan:** Pearson theo chuỗi P&L pip/ngày trong 223 ngày UTC, những ngày không có lệnh lấy 0; mức tương quan được ghi riêng ba cặp. Trung bình |r| càng thấp càng ít đồng biến tuyến tính theo ngày. Các mô hình có thể cùng chịu tổn thất trong những biến động lớn dù hệ số r thấp.
- **Pip ròng gộp:** tổng pip ba phương pháp với khối lượng giả định bằng nhau, BUY vào Ask/ra Bid, SELL vào Bid/ra Ask. Chưa trừ commission, swap, slippage hoặc chi phí vốn/đòn bẩy. `max drawdown` tính bằng pip theo đường lãi lỗ đóng lệnh cộng gộp theo ngày, chưa phải drawdown equity nội nến.
- **Cảnh báo:** tín hiệu đã chọn và tinh chỉnh trên Jan–Oct, tiếp tục dùng Nov 7 ngày để lọc => overfitting / selection bias. Không triển khai live cho đến khi kiểm định độc lập, mô phỏng SL/TP và chi phí thực tế.

## 3 tổ hợp so sánh

| Chỉ tiêu | A: Ít ngày 3 bot cùng thua | B: Ổn định lợi nhuận mỗi tháng | C: Lãi cao + tương quan thấp |
| --- | ---: | ---: | ---: |
| Bot | V11-007 / V11-020 / V11-026 | V11-008 / V11-046 / V11-097 | V11-046 / V11-065 / V11-069 |
| Cả 3 cùng thua | **4** ngày | **7** ngày | **15** ngày |
| Ít nhất 2 cùng thua | 94 ngày | 99 ngày | **84** ngày |
| Trung bình |r| | 0,154 | 0,163 | **0,097** |
| Tương quan r các cặp, theo thứ tự trên | -0,352 / -0,047 / +0,063 | -0,311 / +0,071 / -0,107 | +0,086 / -0,150 / -0,056 |
| Pip Jan–Oct | +1.598,1 | +2.211,9 | +2.975,2 |
| Pip Nov 02–10 | +176,9 | +45,1 | **+277,3** |
| Tổng pip Jan–Oct + Nov 02–10 | +1.775,0 | +2.257,0 | **+3.252,5** |
| Số tháng dương Jan–Oct của **danh mục** | 7/10 | 10/10 | 10/10 |
| Drawdown đóng lệnh (pip) | 358,5 | 206,5 | **202,4** |
| Ngày tổng danh mục âm | 97 | **87** | 95 |

### Từng bot trong mỗi tổ hợp

**A: tối thiểu ngày cả ba cùng thua (duy nhất 1 tổ hợp trong 37.820 tổ hợp có 4 ngày):**
- V11-007 TREND_ACCEL_48_288: vào 13:00 VN, giữ 8h; Jan–Oct +796,1 pip; Nov +72,7 pip.
- V11-020 M9 (momentum của 192 nến M5, ~16 giờ giao dịch): vào 09:15 VN, giữ 10h; Jan–Oct +573,1; Nov +9,1.
- V11-026 REVERSE_ACCEL_3_24: vào 14:30 VN, giữ 8h; Jan–Oct +228,9; Nov +95,1.
- Lưu ý tổng danh mục lỗ tháng 1 (-153,8 pip), tháng 2 (-43,3), tháng 7 (-50,4). Số ngày mất tiền ròng cả danh mục: 97.

**B: ưu tiên tổng danh mục lãi cả 10 tháng Jan–Oct, ít ngày 3 bot cùng thua nhất trong nhóm đó:**
- V11-008 TREND_MA_6_48: vào 12:45 VN, giữ 8h; Jan–Oct +596,2; Nov +12,2.
- V11-046 REVERSE_RANGE_288: vào 15:15 VN, giữ 12h; Jan–Oct +1.198,0; Nov +10,7.
- V11-097 REVERSE_MA_3_48: vào 21:00 VN, giữ 2h; Jan–Oct +417,7; Nov +22,2.
- Tổng danh mục Jan–Oct theo tháng (pip): +212,3; +39,4; +299,6; +279,2; +11,8; +302,0; +290,4; +139,5; +228,3; +409,4.
- Lưu ý một tháng rất mỏng: tháng 5 chỉ +11,8 pip (chưa tính commission/swap).

**C: lợi nhuận cao nhưng giữ tương quan ba cặp thấp, tổng danh mục dương 10/10 tháng:**
- V11-046 REVERSE_RANGE_288: vào 15:15 VN, giữ 12h; Jan–Oct +1.198,0; Nov +10,7.
- V11-065 TREND_ACCEL_48_288: vào 15:45 VN, giữ 8h; Jan–Oct +1.083,6; Nov +105,5.
- V11-069 M1 (momentum 3 nến M5, ~15 phút): vào 12:15 VN, giữ 10h; Jan–Oct +693,6; Nov +161,1.
- Tổng danh mục Jan–Oct theo tháng (pip): +301,4; +153,3; +889,8; +220,7; +111,1; +113,7; +166,7; +351,9; +103,2; +563,4.
- Đây là **tổ hợp có pip cao nhất trong các tổ hợp lãi cả 10 tháng và có |tương quan Pearson của mỗi cặp| <= 0,30** (đã rà soát 37.820 tổ hợp); không phải cực đại pip nếu bỏ qua tương quan.
- Lợi nhuận lớn nhất khi **không** khống chế tương quan là +3.302,7 pip với V11-046 / V11-055 / V11-065 nhưng một cặp r xấp xỉ +0,95 và 37 ngày cả ba cùng thua. Không ưu tiên lựa chọn đó.

## Kết luận

- Đặt ưu tiên tuyệt đối **ít ngày cả ba bot cùng thua**: A.
- Đặt thêm yêu cầu **lãi từng tháng và hạn chế số ngày danh mục lỗ**: B.
- Cân bằng **lợi nhuận cao, độ tương quan thấp, lãi toàn bộ Jan–Oct và Nov**: C. Tổ hợp C có nhiều ngày cả ba cùng thua hơn A và B; thấp tương quan không đồng nghĩa với không có tail risk.
- Cả ba đều có tín hiệu dựa vào nến M5 hoàn tất, giờ vào lệnh khác nhau, có thể có vị thế đồng thời. Trước khi chạy MT5 Hedging, cần tách EA bằng MagicNumber và chỉ hạn chế **mỗi EA tối đa một vị thế của chính EA**, không dùng khóa vị thế toàn symbol; phải xét tổng margin & tổng rủi ro.

Nguồn chính: [100 phương pháp V11](./v11_100_ranked_methods.csv), [log 21.492 lệnh Jan–Oct](./v11_100_trade_log_Jan_Oct_2026.csv.gz), [kho Exness](https://www.exness.global/tick-history/).
