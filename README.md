<p align="center">
  <img width="1792" height="969" alt="image" src="https://github.com/user-attachments/assets/7f938f92-c8bc-45a0-ba45-76fb1a71106e" />
</p>

# Cây Gia Phả cho Home Assistant

Tích hợp tùy chỉnh giúp lưu trữ, quản lý và hiển thị cây gia phả trực tiếp trong Home Assistant. Dữ liệu được lưu cục bộ, có giao diện thêm/chỉnh sửa từng cá thể và một thẻ Lovelace riêng để xem toàn bộ sơ đồ.

**Home Assistant tối thiểu (bản cập nhật này):** `2026.11.0` — đã đối chiếu API với Home Assistant Core 2026.11.0.

## Tính năng

- Tạo cây gia phả và người gốc ngay trong luồng cấu hình.
- Thêm, sửa và xóa từng cá thể từ trang cấu hình tích hợp.
- Khai báo cha, mẹ, nhiều vợ/chồng, thứ tự vợ/chồng, anh chị em và con nuôi.
- Hỗ trợ ngày sinh/ngày mất đầy đủ hoặc chỉ nhập năm, tháng và ngày đã biết.
- Tải ảnh đại diện; tự dùng ảnh nam, nữ hoặc ảnh mặc định khi chưa có ảnh.
- Tạo một sensor tổng quan và một sensor riêng cho từng cá thể.
- Thẻ Lovelace có kéo để di chuyển, cuộn chuột để thu phóng, nút thu gọn nhánh và popup chi tiết.
- Bố cục nhiều vợ/chồng và các nhánh con được tính toán độc lập để hạn chế chồng chéo.
- Tùy chỉnh tiêu đề, nội dung, phông chữ, màu sắc, kích thước ảnh và khoảng cách sơ đồ.
- Có bản dịch tiếng Việt và tiếng Anh.
- Cơ sở dữ liệu SQLite và ảnh được tạo tự động trong thư mục `cay_gia_pha/` dưới **thư mục cấu hình** Home Assistant (thường là `/config/cay_gia_pha/`). Hãy sao lưu thư mục này cùng cấu hình Home Assistant trước khi cập nhật.



---

## Cài đặt trên Marketplace (Home Assistant 2026.11+)

Home Assistant 2026.11 đã tích hợp HACS thành **Marketplace**. **Không cài lại HACS custom integration** trên Home Assistant 2026.11 trở lên.

[![Mở repository trong Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=khaisilk1910&repository=cay-gia-pha&category=integration)

1. Mở **Settings → Marketplace**; tìm **Cây Gia Phả**. Nếu chưa xuất hiện trong danh mục công khai, thêm `https://github.com/khaisilk1910/cay-gia-pha` trong **Custom repositories**, chọn loại **Integration**.
2. Cài bản release tương ứng và khởi động lại Home Assistant khi Marketplace yêu cầu (đặc biệt khi cập nhật integration đã tải).
3. Vào **Settings → Devices & services → Add integration**, tìm **Cây Gia Phả**.
4. Thêm thẻ qua **Dashboard → Edit → Add card → Cây Gia Phả**. Thẻ Lovelace được phục vụ cùng integration, **không** phải cài lại như một HACS dashboard plugin riêng.

### Cài thủ công / cập nhật từ bản trước

Chép `custom_components/cay_gia_pha/` vào `/config/custom_components/cay_gia_pha/` và khởi động lại Home Assistant. **Sao lưu cả `/config/cay_gia_pha/` và cấu hình Home Assistant trước khi nâng cấp.** Không xóa config entry và không xóa thư mục này khi cập nhật.

Nếu đã từng thêm tài nguyên thẻ bằng tay, vào **Dashboard → Resources** để xóa tài nguyên trùng có tiền tố `/cay_gia_pha_static/cay-gia-pha-card.js`, giữ lại một mục duy nhất. Với chế độ Lovelace YAML, nếu thẻ chưa tải, thêm module sau vào danh sách `resources` của YAML:

```yaml
resources:
  - url: /cay_gia_pha_static/cay-gia-pha-card.js?v=2026.11.0
    type: module
```

Trường hợp bình thường, integration đăng ký tài nguyên này tự động. Refresh trình duyệt sau khi cập nhật.

---

## Thiết lập cây gia phả

1. Thêm tích hợp **Cây Gia Phả**.
2. Nhập tên cây và thông tin người gốc.
3. Mở trang cấu hình của tích hợp để thêm các cá thể tiếp theo.
4. Với mỗi người, chọn đúng cha, mẹ, vợ/chồng và thứ tự quan hệ.
5. Khi dữ liệu thay đổi, sensor và thẻ sơ đồ sẽ tự cập nhật.

## Thêm thẻ vào Dashboard

Tích hợp tự đăng ký tệp JavaScript của thẻ, vì vậy không cần thêm Lovelace Resource thủ công.

Trong Dashboard, chọn **Add card** và tìm **Cây Gia Phả**.

## Dữ liệu và quyền riêng tư

- Cơ sở dữ liệu và ảnh được lưu cục bộ trong thư mục cấu hình Home Assistant.
- Tích hợp không gửi dữ liệu gia phả đến dịch vụ bên ngoài.
- Hãy sao lưu cấu hình Home Assistant trước khi nâng cấp hoặc chỉnh sửa dữ liệu lớn.
- Không nên đưa ảnh, ngày sinh hoặc thông tin gia đình thật vào issue công khai trên GitHub.


## Báo lỗi và đóng góp

Trước khi tạo issue, hãy kiểm tra log Home Assistant và xóa thông tin cá nhân khỏi ảnh chụp màn hình.

## Giấy phép

Dự án được phát hành theo giấy phép [MIT](LICENSE).

## Kiểm tra và chẩn đoán

Bản này giảm công việc khởi động bằng cách chuyển đăng ký tài nguyên Lovelace sang tác vụ nền (không chặn việc tạo sensor), giữ truy cập SQLite trong executor và chỉ làm mới snapshot khi dữ liệu thay đổi. Việc tải SQLite lần đầu vẫn cần hoàn thành trước khi sensor có dữ liệu chính xác; không có cam kết khởi động bằng 0 ms.

Để bật log chẩn đoán, thêm vào `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.cay_gia_pha: debug
```

Nhật ký ghi thời gian tải, số người, số phiên bản dữ liệu và lỗi SQLite/Lovelace, không cố ý ghi tên/ảnh cá nhân. Có thể tắt `debug` sau khi kiểm tra. Nếu log báo cơ sở dữ liệu không đọc được hoặc còn người nhưng entry không có subentry, **không xóa `/config/cay_gia_pha/`**; sao lưu và xử lý nguyên nhân trước.

Cập nhật bản release: trước khi tạo Git tag/release, sửa `manifest.json` sao cho `version` khớp với tag (bỏ tiền tố `v` nếu có). Tệp GitHub Actions sẽ kiểm tra, không tự di chuyển tag sau khi đã phát hành.
