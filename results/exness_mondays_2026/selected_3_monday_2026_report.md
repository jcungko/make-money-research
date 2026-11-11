# Backtest 3 phương pháp thứ Hai — 2026 đến 09/11

- Dữ liệu Exness tick lịch sử, thời gian UTC, 45 thứ Hai từ 05/01 tới 09/11.
- Ba bot #11 EURUSD H4 SMA3 (16:30 UTC, 240 phút), #6 USDJPY H1 BUY (08:30 UTC, 120 phút), #18 GBPUSD M30 SMAR12 (09:00 UTC, 90 phút).
- Từng lệnh đã mô hình hóa Bid/Ask qua giá đầu tiên của thanh M5 ở thời điểm vào/ra, **chưa tính trượt giá, phí khác, swap, MT5 execution**.
- Kết quả cộng pip của 3 bot chỉ là chỉ số minh họa, không phải số USD hay P&L chuẩn hóa theo pip-value, lot hoặc rủi ro.

## Tổng hợp
| Phương pháp | Số lệnh | Thắng | Thua | Pip ròng | PF |
|---|---:|---:|---:|---:|---:|
| #11 EURUSD | 45 | 31 | 14 | +301.6 | 6.42 |
| #6 USDJPY | 45 | 32 | 13 | +200.2 | 2.09 |
| #18 GBPUSD | 45 | 31 | 14 | +204.8 | 2.63 |

Cộng cơ học: **706.6 pip**, 38 tuần tổng dương/45, 7 tuần âm; tháng nào trong 11 tháng từ tháng 1 đến tháng 11 (mới 2 tuần) cũng tổng dương; 3 bot cùng âm một tuần ngày 2026-01-26. Chuỗi tổng dương dài nhất 22 tuần. Mức tuần âm sâu nhất -30.3 pip, tuần dương cao nhất +90.0 pip. Maximum peak-to-trough drawdown **63.6 pip** của chuỗi tổng lãi theo tuần; không phải DD trong phiên hay USD. PF trên chuỗi pip cộng là 6.59.

**Cảnh báo out-of-sample:** Những phương pháp này được chọn từ chính dữ liệu 2026, do đó kết quả 2026 là in-sample có selection bias. Chưa thể kết luận sẽ bền vững; cần kiểm tra trên năm 2025 hoặc dữ liệu mới sau ngày khóa thông số.

## Theo tháng
| Tháng | Thứ Hai | #11 EURUSD | #6 USDJPY | #18 GBPUSD | Tổng pip | Tuần tổng dương |
|---|---:|---:|---:|---:|---:|---:|
| 2026-01 | 4 | 15.2 | -29.4 | 16.2 | 2 | 2/4 |
| 2026-02 | 4 | 42.2 | 20.4 | -20.7 | 41.9 | 3/4 |
| 2026-03 | 5 | 75 | -64.3 | 48.2 | 58.9 | 3/5 |
| 2026-04 | 4 | 53.2 | 6.1 | 16.1 | 75.4 | 4/4 |
| 2026-05 | 4 | 17.2 | 26.4 | 5.6 | 49.2 | 3/4 |
| 2026-06 | 5 | -3.8 | -13 | 68.8 | 52 | 4/5 |
| 2026-07 | 4 | 31.2 | 13.8 | 4.9 | 49.9 | 4/4 |
| 2026-08 | 5 | 18.2 | 60 | 29.9 | 108.1 | 5/5 |
| 2026-09 | 4 | 4.7 | 93.3 | 10 | 108 | 4/4 |
| 2026-10 | 4 | 24.5 | 54.3 | 6.9 | 85.7 | 4/4 |
| 2026-11 | 2 | 24 | 32.6 | 18.9 | 75.5 | 2/2 |

Dữ liệu từng tuần và từng tháng có trong hai CSV cùng thư mục.