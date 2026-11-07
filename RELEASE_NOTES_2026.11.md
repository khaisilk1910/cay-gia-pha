# Ghi chú cập nhật Cây Gia Phả — 2026.11.0

## Môi trường đối chiếu

- Home Assistant Core **2026.11.0** (bản phát hành 04/11/2026), Python >= 3.14.2 theo `pyproject.toml` của Core.
- Marketplace tích hợp từ Home Assistant 2026.11; metadata `hacs.json` ở thư mục gốc, mã integration đặt tại `custom_components/cay_gia_pha/`.
- Các API đối chiếu trực tiếp với Home Assistant Core tag `2026.11.0`: `config_entries`, `frontend`, `lovelace.resources` và `file_upload`.

## Thay đổi chính

1. **Khởi động:** loại bỏ thao tác băm file JS khi thiết lập entry; đăng ký Lovelace resource bằng tác vụ nền theo vòng đời entry, không chặn sensor. SQLite/schema và chỉ mục quan hệ chạy qua executor; không bật polling để tải lại liên tục.
2. **Marketplace:** cập nhật `manifest.json`, `hacs.json`, mã GitHub, workflow kiểm tra HACS/hassfest. Release tag chỉ được kiểm tra khớp `manifest.version` thay vì tự động sửa tag đã công bố.
3. **SQLite:** thông báo lỗi đọc cơ sở dữ liệu thay vì giả vờ cây trống; bảo toàn dữ liệu cũ lúc khởi động nếu thiếu toàn bộ subentry; log migration/thời gian/revision; chỉ tăng revision khi có thay đổi; đóng kết nối sau mỗi giao dịch. Trạng thái cập nhật config subentry được tuần tự hóa bằng `asyncio.Lock`.
4. **Ảnh:** kiểm tra định dạng ảnh qua chữ ký tệp và giới hạn kích thước, ghi thay thế an toàn bằng tệp tạm; truy cập qua endpoint yêu cầu xác thực/chữ ký. Ảnh chỉ được xóa nếu không còn ai tham chiếu.
5. **Lovelace:** metadata custom card, editor cấu hình, grid options, title mặc định theo tên cây; thao tác bàn phím/focus trong popup; xử lý dữ liệu WS cũ và backoff có giới hạn khi kết nối lỗi; bỏ sửa `prototype` toàn cục của HA để không ảnh hưởng selector hệ thống.
6. **Chẩn đoán:** thông báo rõ lỗi sqlite, tải ảnh, đăng ký resource, request WS; log debug thời gian tải và số người (không chủ đích ghi họ tên/ảnh cá nhân).

## Kết quả kiểm thử

```sh
python -m compileall -q custom_components/cay_gia_pha
node --input-type=module --check < custom_components/cay_gia_pha/frontend/cay-gia-pha-card.js
node tests/test_frontend.mjs
python -m pytest -q
```

- **27/27** kiểm thử Python thành công trên Python 3.13 ở môi trường làm việc.
- **JS module syntax + smoke test custom card** thành công với Node.js 22.
- Kiểm tra JSON manifest, HACS và đối chiếu đủ khóa dịch giữa `strings.json`, tiếng Việt, tiếng Anh.
- GitHub Actions được cấu hình để tiếp tục chạy kiểm tra HACS/hassfest và CI với Python 3.14.

## Những gì chưa thể xác nhận trong môi trường kiểm thử

- **Chưa chạy Home Assistant Core 2026.11.0 thực tế trong container** để kiểm tra lifecycle frontend/dashboard, tương tác UI trên trình duyệt, network hoặc nâng cấp cơ sở dữ liệu thật của người dùng.
- **Chưa chạy online GitHub Actions/HACS action/hassfest**: chỉ có thể thực hiện sau khi đẩy mã nguồn lên GitHub. Danh mục Marketplace công khai còn phụ thuộc quy trình xét duyệt `hacs/default`.
- Hiệu năng khởi động được tối ưu theo code path nhưng **chưa có số liệu benchmark trên thiết bị Home Assistant thực tế**.

## Khuyến nghị triển khai

1. Sao lưu `/config/cay_gia_pha/` và cấu hình HA (`.storage/core.config_entries`) bằng một bản sao lưu Home Assistant hợp lệ.
2. Thử trên một instance HA 2026.11 đã sao lưu hoặc bản staging, rồi kiểm tra `Settings > Devices & services` và `Dashboard > Edit > Add card`.
3. Nếu sau khôi phục SQLite thấy cảnh báo còn người nhưng không có subentry, không xóa cơ sở dữ liệu. Khắc phục qua thiết lập lại flow có hỗ trợ khôi phục sau khi sao lưu.
4. Đẩy code, để các workflow kiểm tra repository chạy thành công. Khi phát hành, tạo tag **`2026.11.0`** hoặc **`v2026.11.0`** trùng version manifest.
5. Bật `custom_components.cay_gia_pha: debug` tạm thời trong `logger` để thu thập log khi cần; ẩn thông tin gia đình trước khi gửi issue.
