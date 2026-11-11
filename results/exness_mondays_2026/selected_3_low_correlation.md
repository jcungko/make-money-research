# Dự án 2 — Bộ 3 chiến lược đa dạng hóa, thứ Hai 2026

Ngày phân tích: 2026-11-11. Dữ liệu: Exness historical tick archive, sau bổ sung tháng bị thiếu; Bid/Ask thứ Hai UTC, 2026-01-05 tới 2026-11-09, 45 phiên. Nguồn kết quả gốc: `top50_daily_pips.csv` và `ranked_30_balanced.csv` trong cùng thư mục. Kiểm tra 4.060 bộ ba từ 30 ứng viên. Đây là dữ liệu nội mẫu, không phải kiểm định độc lập, không có bảo đảm kết quả tương lai.

## Bộ được chọn (một cặp tiền cho mỗi bot)

| Bot nguồn | Cặp | Khung | Quy tắc | Vào UTC | Giữ phút | Ngày lãi /45 | Tổng pip sau Bid/Ask | PF | Tuần lãi trong 8 tuần cuối |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| #11 | EURUSD | H4 | SMA3 | 16:30 | 240 | 31 | +301.6 | 6.42 | 8/8 |
| #6 | USDJPY | H1 | BUY | 08:30 | 120 | 32 | +200.2 | 2.09 | 8/8 |
| #18 | GBPUSD | M30 | SMAR12 | 09:00 | 90 | 31 | +204.8 | 2.63 | 5/8 |

Định nghĩa: SMA3 giao dịch theo chiều giá đóng cửa nến H4 đã hoàn tất so với SMA3 nến H4; BUY cố định; SMAR12 giao dịch ngược chiều SMA12 trên M30. Các lệnh thoát theo thời gian; mỗi thứ Hai một lệnh/mỗi bot.

## Tương quan Pearson trên 45 chuỗi P&L ngày thứ Hai

| | #11 | #6 | #18 |
|---|---:|---:|---:|
| #11 | 1.00000 | +0.01855 | -0.08744 |
| #6 | +0.01855 | 1.00000 | -0.00009 |
| #18 | -0.08744 | -0.00009 | 1.00000 |

Trung bình ba tương quan tuyệt đối: 0.03536; giá trị tuyệt đối lớn nhất: 0.08744. 3 bot cùng thua **1/45** thứ Hai: 2026-01-26; P&L lần lượt -2.0, -19.0, -9.3 pip.

Minh họa cộng trực tiếp pip của 3 bot (chưa quy ra tiền, không phải danh mục theo rủi ro): +706.6 pip, 38/45 thứ Hai tổng dương, 7/45 âm; 8/8 thứ Hai gần nhất tổng dương (+223.4 pip). Kết quả cộng pip không tương ứng lợi nhuận USD vì pip value và số lot từng cặp khác nhau; không tính phí swap, trượt giá, MT5 fills và drawdown nội phiên.

## Kiểm định độ ổn định của tương quan

| Cặp | 45 tuần | 30 tuần đầu | 15 tuần cuối | 8 tuần cuối |
|---|---:|---:|---:|---:|
| #11 / #6 | +0.019 | +0.151 | -0.062 | +0.014 |
| #11 / #18 | -0.087 | -0.112 | +0.050 | -0.203 |
| #6 / #18 | -0.000 | -0.048 | +0.180 | +0.785 |

Đáng chú ý: #6/#18 có tương quan cao trong 8 tuần gần nhất, dù gần như bằng 0 trên 45 tuần. Mẫu 8 tuần rất ngắn; điều này cho thấy tương quan không ổn định và không chứng minh sự độc lập. Cần kiểm tra lãi/lỗ khi đồng thời mở lệnh 09:00–10:30 UTC của #6 và #18.

## Quy tắc chọn

Ưu tiên một bot/mỗi cặp, hiệu suất riêng đã dương trên 45 tuần, thứ hạng cân bằng trong Top 30, tương quan Pearson pip P&L tuyệt đối thấp và số ngày cùng âm ít, cùng với kết quả 8 thứ Hai gần nhất. Bộ này là quyết định cân bằng giữa chất lượng và đa dạng hóa, **không phải** bộ tuyệt đối ít tương quan nhất. Nếu tối thiểu hóa trung bình |r| đơn thuần trong 4.060 tổ hợp thì #7, #10, #3 đạt khoảng 0.01146 nhưng chứa hai bot USDJPY, yếu tố cần xem xét về phơi nhiễm tỷ giá.

## Việc chưa hoàn tất

- Backtest nguyên quy tắc trên năm 2025 (out-of-sample theo phương pháp lựa chọn).
- Mô phỏng trên tick/terminal MT5 của tài khoản Exness, kiểm tra giờ server, spread biến đổi, SL/TP, rủi ro/lệnh, độ trễ và gap.
- Kiểm tra phụ thuộc trong lệnh/khủng hoảng, tương quan dài hạn, chuẩn hóa vốn rủi ro và không mặc định ba cặp tiền độc lập.
- Không dùng kết quả nội mẫu như chứng nhận để tự động giao dịch thật.
