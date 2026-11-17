# Giữ lại ứng viên EMA MTF · EURUSD M15 — CHƯA ĐƯỢC XÁC NHẬN TRIỂN KHAI

**Trạng thái:** HOLD / lưu để nghiên cứu sau; không chỉnh sửa hoặc giao dịch tự động.
**Ngày ghi nhận:** 2026-11-17.
**EA gốc:** https://github.com/111aaa327/mt5-ea-open-source/blob/98cc370881a3ceb1d75c028b5b08e48f511a5114/Experts/EURUSD_EMA_MTF_5_8_21_55_EA_v2.mq5

- Thị trường và timeframe: EURUSD M15.
- Khối lượng người dùng yêu cầu: **0.01 lots cố định cho mỗi lệnh** (ghi đè cách tính lot mặc định dựa trên % rủi ro; thay đổi khối lượng giao dịch, không thay logic tín hiệu). Khi chạy thử trên MT5 cần kiểm tra tham số lot thực tế và việc chọn chế độ fixed lot.
- Bộ lọc tín hiệu từ mã nguồn: EMA 5/8/21/55, D1/H8/H1/M15 alignment, RSI và pullback.
- Số liệu nghiên cứu trước đó: mô phỏng Python nến Bid/Ask, **KHÔNG phải Strategy Tester MT5 real ticks**. Tháng 08-10/2026: 22 lệnh, +949.24 USD *trước phí* trong mô phỏng với lot theo risk sizing, KHÔNG phải kết quả 0.01 lot. Tháng 11 tới cuối 16/11/2026: 4 lệnh, 0.01 lot xấp xỉ +0.12 USD sau phí mô phỏng 7 USD/lot; đây chỉ là phép quy đổi dựa trên các giao dịch đã mô phỏng, KHÔNG phải báo cáo tái chạy native.
- Chưa xác thực biên dịch trong MetaEditor, cũng chưa kiểm toán forward/live.
- Không trộn ứng viên này với kết quả bot mới; giữ nguyên cho vòng kiểm chứng độc lập sau.
