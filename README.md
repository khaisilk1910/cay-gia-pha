<p align="center">
  <img src="custom_components/cay_gia_pha/brand/logo.png" alt="Cây Gia Phả" width="420">
</p>

# Cây Gia Phả cho Home Assistant

Tích hợp tùy chỉnh giúp lưu trữ, quản lý và hiển thị cây gia phả trực tiếp trong Home Assistant. Dữ liệu được lưu cục bộ, có giao diện thêm/chỉnh sửa từng cá thể và một thẻ Lovelace riêng để xem toàn bộ sơ đồ.

**Phiên bản:** `0.3.10`  
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
    
---

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

## Thiết lập cây gia phả

1. Thêm tích hợp **Cây Gia Phả**.
2. Nhập tên cây và thông tin người gốc.
3. Mở trang cấu hình của tích hợp để thêm các cá thể tiếp theo.
4. Với mỗi người, chọn đúng cha, mẹ, vợ/chồng và thứ tự quan hệ.
5. Khi dữ liệu thay đổi, sensor và thẻ sơ đồ sẽ tự cập nhật.

## Thêm thẻ vào Dashboard

Tích hợp tự đăng ký tệp JavaScript của thẻ, vì vậy không cần thêm Lovelace Resource thủ công.

Trong Dashboard, chọn **Add card** và tìm **Cây Gia Phả**. Có thể dùng YAML tối giản:

```yaml
type: custom:cay-gia-pha-card
title: Gia Phả Gia Đình
subtitle: Theo dấu các thế hệ trong gia đình qua năm tháng.
show_summary: true
show_dates: true
show_age: false
show_details: true
show_decorations: true
deceased_grayscale: true
show_zoom: true
```

Một số tùy chọn giao diện khác:

```yaml
title_font: noto-serif
content_font: noto-sans
title_font_size: 46
subtitle_font_size: 14
avatar_size: 70
node_width: 156
horizontal_spacing: 34
vertical_spacing: 84
border_radius: 18
background_color: "#fbfaf6"
text_color: "#171512"
muted_text_color: "#655f55"
line_color: "#aaa493"
border_color: "#d9d3c5"
male_color: "#557d96"
female_color: "#a97887"
other_color: "#7d7294"
decoration_color: "#d8d2c1"
```

## Dữ liệu và quyền riêng tư

- Cơ sở dữ liệu và ảnh được lưu cục bộ trong thư mục cấu hình Home Assistant.
- Tích hợp không gửi dữ liệu gia phả đến dịch vụ bên ngoài.
- Hãy sao lưu cấu hình Home Assistant trước khi nâng cấp hoặc chỉnh sửa dữ liệu lớn.
- Không nên đưa ảnh, ngày sinh hoặc thông tin gia đình thật vào issue công khai trên GitHub.

## Cập nhật phiên bản

Khi phát hành phiên bản mới, cần cập nhật đồng thời:

- `version` trong `custom_components/cay_gia_pha/manifest.json`.
- `FRONTEND_MODULE_URL` trong `const.py`.
- `CARD_VERSION` và phiên bản URL ảnh mặc định trong `frontend/cay-gia-pha-card.js`.
- `CHANGELOG.md`.

## Báo lỗi và đóng góp

Trước khi tạo issue, hãy kiểm tra log Home Assistant và xóa thông tin cá nhân khỏi ảnh chụp màn hình. Xem thêm [CONTRIBUTING.md](CONTRIBUTING.md) và [SECURITY.md](SECURITY.md).

## Giấy phép

Dự án được phát hành theo giấy phép [MIT](LICENSE).
