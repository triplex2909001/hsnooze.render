# hsnooze.render

Bộ dựng video 4K UHD 90 phút (15 Parts) chuẩn phong cách **Slow Ken Burns ASMR** cho kênh **HistorySnooze** (100% Cloud Native, 0% VPS).

## 🚀 Tính Năng Cốt Lõi
1. **Kiểm Toán Tài Sản GK6 (PreAssembly Asset Audit):** Đảm bảo đủ 15 file WAV voiceover và tối thiểu 45 ảnh keyframes 4K trước khi dựng.
2. **Chuyển Động Slow Ken Burns ASMR (kenburns_asmr.py):**
   - Scale ảnh lên 8000x4500 để triệt tiêu hiện tượng rung hạt sub-pixel.
   - Zoom vi mô êm dịu từ 1.00 lên tối đa 1.04 trong 75–90 giây.
   - Chuẩn 4K UHD (3840x2160), 30fps, 16:9.
3. **Dựng Độc Lập 15 Video Chunks (chunk_renderer.py):** Từng Part được dựng riêng với cơ chế **Smart Delta Restart** (bỏ qua part đã render hợp lệ > 10 MB).
4. **Ghép Nối Master Siêu Tốc 30 Giây (master_assembler.py):** Tạo khoảng lặng 5.0s (`silence_5s.mp4`), ghép 15 chunks bằng kỹ thuật Stream Copy (`ffmpeg -c copy`), hoàn tất xuất file 90 phút chỉ trong 30 giây thay vì mất nhiều giờ re-encoding.
5. **Kiểm Toán Thành Phẩm GK7 (Final Master Audit):** Thời lượng chuẩn 80–95 phút, độ phân giải 3840x2160, âm thanh Stereo AAC 44.1kHz.

## 🔐 GitHub Secrets Cần Cấu Hình
- `GDRIVE_SERVICE_ACCOUNT_KEY`: Khóa Service Account JSON để tải ảnh/audio và upload `master_final_90min.mp4` lên Google Drive.

## 🕹️ Cách Kích Hoạt
Truy cập tab **Actions** -> Chọn workflow **HistorySnooze 4K ASMR Video Render Pipeline** -> Bấm **Run workflow**:
- `project_folder_id`: ID thư mục dự án trên Google Drive
- `row_index`: Số hàng trên Google Sheet (để cập nhật Status = `Ready`, Video = `Done`)
