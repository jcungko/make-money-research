# EURUSDm Exness — lịch sử tick 2026 (dữ liệu nghiên cứu V8)

**Đã thu thập ngày 10/11/2026.** Nguồn lưu trữ Exness công khai: [Tick history](https://www.exness.global/tick-history/), [tick archives](https://ticks.ex2archive.com/ticks/EURUSDm/2026/Exness_EURUSDm_2026.zip).

- **Kỳ dữ liệu đã xử lý:** 01/01/2026–09/11/2026 23:59 UTC; không có tệp tick ngày 10/11 hoàn chỉnh tại thời điểm lấy.
- **Sản phẩm:** `EURUSDm` (Exness Standard, không phải EURUSD Raw Spread).
- **Số lượng tick Bid/Ask:** **10.709.217**.
- **Nến được dựng từ tick:** **M5: 63.874**, **M15: 21.318**, **H1: 5.330**.
- **Tệp tổng hợp:** [exness_eurusdm_2026_m5_m15_h1.zip](./exness_eurusdm_2026_m5_m15_h1.zip) (1.847.482 bytes).
- **SHA256 của tệp ZIP:** `302d71ecf3bd4f57d10adbf4170dde696d5d7137cdae91d1de0c55a1a8d16499`.
- Gói ZIP có 33 tệp CSV theo tháng/khung, `manifest.json` lưu URL gốc và SHA256 từng tệp lưu trữ, cùng `README.txt`.

## Đối chiếu chất lượng

Nguồn ưu tiên là **các ZIP theo tháng 01–11/2026**. Riêng tệp tháng 03 chỉ kéo dài đến 29/03, vì vậy đã bổ sung **128.302 tick ngày 30–31/03** từ [ZIP năm 2026](https://ticks.ex2archive.com/ticks/EURUSDm/2026/Exness_EURUSDm_2026.zip), không chồng lấn timestamp tháng 03 đã có.

Một số ZIP theo tháng và ZIP tổng năm **có số lượng tick khác nhau** cho cùng tháng; đây là điểm chưa kiểm toán xong. Tệp ngày 10/11 mang dữ liệu nén chưa hoàn tất (thiếu phần kết ZIP), **không được đưa vào bộ dữ liệu đã xác minh**. Thời gian nghỉ cuối tuần là bình thường với EURUSD.

**Cấu trúc mỗi dòng:** thời gian mở nến UTC, Bid OHLC, Ask OHLC, spread mở/đóng/trung bình/cao nhất theo pip, tick count. Dữ liệu lưu trữ phản ánh giá tham khảo, không phải kiểm định khớp lệnh MT5. Chưa có backtest hay chứng minh lợi nhuận, không can thiệp vào EA đang chạy.

**Nguồn:** [Exness Tick history hướng dẫn](https://get.exness.help/hc/en-us/articles/360021547851-Tick-history).