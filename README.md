<p align="center">
  <img src="custom_components/cay_gia_pha/brand/logo.png" alt="Cây Gia Phả" width="420">
</p>

# Cây Gia Phả cho Home Assistant

Tích hợp tùy chỉnh giúp lưu trữ, quản lý và hiển thị cây gia phả trực tiếp trong Home Assistant. Dữ liệu được lưu cục bộ, có giao diện thêm/chỉnh sửa từng cá thể và một thẻ Lovelace riêng để xem toàn bộ sơ đồ.

**Home Assistant tối thiểu:** `2025.3.0`

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



---

## Cài đặt

### Cài tự động

  - Nhấn nút bên dưới để thêm vào HACS trên Home Assistant.

  [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=khaisilk1910&repository=cay-gia-pha&category=integration)

  - Sau khi thêm trong HACS và khởi động lại Home Assistant
     
  - Vào Settings -> Integrations -> Add integration -> Tìm `Cây Gia Phả`

## Cài đặt bằng HACS

1. Mở **HACS** → **Integrations**.
2. Chọn menu ba chấm → **Custom repositories**.
3. Nhập URL repository GitHub của bạn và chọn loại **Integration**.
4. Tìm **Cây Gia Phả**, chọn **Download** rồi khởi động lại Home Assistant.
5. Vào **Settings** → **Devices & services** → **Add integration** và tìm **Cây Gia Phả**.

## Cài đặt thủ công

Sao chép thư mục:

```text
custom_components/cay_gia_pha
```

vào thư mục cấu hình Home Assistant:

```text
/config/custom_components/cay_gia_pha
```

Sau đó khởi động lại Home Assistant và thêm tích hợp từ **Settings → Devices & services**.

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
