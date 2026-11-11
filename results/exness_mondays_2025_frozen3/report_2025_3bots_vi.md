# Kết quả backtest ngoài mẫu lịch sử năm 2025: 3 bot thứ Hai

**Đã kiểm tra:** 52/52 thứ Hai, 06/01–29/12/2025 (UTC). Quy tắc bot được đóng băng sau quá trình lựa chọn trên dữ liệu năm 2026; không chỉnh giờ giao dịch, điều kiện hoặc thời gian giữ lệnh. Replay bằng 36 tệp ZIP tháng Exness (EURUSD, USDJPY, GBPUSD), dựa trên Bid/Ask và OHLC dựng từ tick. Không có lệnh thực, không có SL/TP, không bao gồm slippage, swap và phí thực thi khác.

| Bot | Khung | Quy tắc | Giờ mở (UTC) | Giữ | Thắng | Thua | Hòa | Pip sau Bid/Ask | Profit Factor |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| #11 EURUSD | H4 | SMA3 | 16:30 | 240 phút | 25 | 26 | 1 | +78.3 | 1.307 |
| #6 USDJPY | H1 | BUY | 08:30 | 120 phút | 23 | 29 | 0 | -121.9 | 0.780 |
| #18 GBPUSD | M30 | SMAR12 | 09:00 | 90 phút | 17 | 35 | 0 | -211.2 | 0.526 |

**Danh mục cộng pip:** -254.8 pip, 23 tuần dương/52, 29 tuần âm/52, PF 0.689. Năm 2025 chỉ 5 tháng tổng dương/12, 7 tháng âm/12. Mức tuần âm nhất -195.5 pip (27/01/2025). Maximum peak-to-trough drawdown theo chốt cuối tuần là 340.6 pip; đây không phải DD USD hay DD nội phiên. 3 bot cùng lỗ 10 thứ Hai năm 2025.

## Đối chiếu cùng số tuần 45
So sánh 45 thứ Hai đầu năm 2025 (06/01–10/11) với 45 thứ Hai 2026 (05/01–09/11), dù hai chuỗi không hoàn toàn trùng lịch thị trường.

| | 2025 45 thứ Hai | 2026 45 thứ Hai |
|---|---:|---:|
| #11 EURUSD | +128.8 | +301.6 |
| #6 USDJPY | -93.7 | +200.2 |
| #18 GBPUSD | -211.9 | +204.8 |
| Tổng pip (chỉ số mô phỏng) | **-176.8** | **+706.6** |
| Tuần tổng dương | 21/45 | 38/45 |

**Kết luận:** Bộ #11/#6/#18 không đạt điều kiện lợi nhuận dương ở cả năm 2025 và 2026, và chưa đủ cơ sở để triển khai tiền thật. #11 riêng năm 2025 chỉ còn PF 1.307 và 25/52 ngày lãi; không nên suy diễn từ hiệu suất 2026 sau bước chọn nhiều ứng viên.

## Pip theo tháng năm 2025
| Tháng | #11 EURUSD | #6 USDJPY | #18 GBPUSD | Tổng pip | Tuần dương |
|---|---:|---:|---:|---:|---:|
| 01 | -16.3 | -124.4 | -58.5 | -199.2 | 2/4 |
| 02 | -5.1 | -35.9 | +0.6 | -40.4 | 2/4 |
| 03 | -57.5 | -25.9 | +31.9 | -51.5 | 1/5 |
| 04 | +50.1 | +21.0 | -21.9 | +49.2 | 3/4 |
| 05 | -15.1 | +4.1 | -39.8 | -50.8 | 1/4 |
| 06 | +70.3 | +25.7 | -33.4 | +62.6 | 3/5 |
| 07 | +13.9 | +33.5 | -2.5 | +44.9 | 2/4 |
| 08 | +48.2 | +17.1 | -38.4 | +26.9 | 2/4 |
| 09 | +12.3 | -1.4 | -38.6 | -27.7 | 2/5 |
| 10 | +30.5 | -16.3 | -26.8 | -12.6 | 1/4 |
| 11 | +9.2 | +6.2 | +10.6 | +26.0 | 3/4 |
| 12 | -62.2 | -25.6 | +5.6 | -82.2 | 1/5 |

## Audit dữ liệu
- 36 ZIP tháng; raw archive checksums nằm trong `report_2025_3bots.json`.
- Số tick của các thứ Hai được đọc: EURUSD 3.476.755; USDJPY 4.680.407; GBPUSD 3.689.676.
- 14/04/2025 EURUSD thiếu tick trong 14:05–14:15 UTC. H4 gốc vẫn tồn tại với các tick thực trong phần còn lại của khung; không thêm tick giả. Giao dịch #11 ở ngày đó được tính +5.6 pip.
- Đã replay phương pháp tính nến từ mã 2025 lên 45 ngày 2026, so khớp từng pip với kết quả cũ cho cả ba bot (0 sai khác).
- Không nên xem số pip cộng của EURUSD/USDJPY/GBPUSD là cùng một lượng USD/lệnh; pip-value và lot có thể khác nhau, và tương quan thực theo P&L USD cũng khác.

**Tài liệu liên quan:**
- `trades_2025_3bots.csv`: từng ngày từng lệnh.
- `monthly_2025_3bots.csv`: theo tháng.
- `report_2025_3bots.json`: chi tiết và checksum.
- `research/exness_mondays_2025_frozen3.py`: mã tái lập.

Nguồn Exness chính thức: https://www.exness.global/tick-history/ . Exness lưu ý tick history là dữ liệu tham khảo, không bảo đảm giá khớp lệnh.


## Tương quan của bộ ba trong năm 2025
Tương quan Pearson tính trên 52 lãi/lỗ pip từng thứ Hai:

| Cặp bot | r trong năm 2025 | r trong 2026 (45 tuần) |
|---|---:|---:|
| #11 EURUSD / #6 USDJPY | +0.253 | +0.019 |
| #11 EURUSD / #18 GBPUSD | -0.283 | -0.087 |
| #6 USDJPY / #18 GBPUSD | +0.214 | -0.000 |

Trung bình ba giá trị |r| năm 2025 khoảng **0.250**, cao hơn rõ rệt mức **0.035** trong năm 2026. Mẫu 52 tuần vẫn nhỏ và tương quan có thể thay đổi theo thời kỳ. Có **10 thứ Hai cả ba bot cùng âm** trong năm 2025; đây là bằng chứng thực nghiệm chống lại giả định ba bot độc lập về lãi/lỗ.
