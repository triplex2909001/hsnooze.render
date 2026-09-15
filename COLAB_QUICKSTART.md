# 🚀 HistorySnooze 4K Video Renderer — Google Colab Guide (GHA Parity)

Bản hướng dẫn chạy Render 4K trên **Google Colab GPU (Tesla T4 / L4)** đồng bộ 100% với **GitHub Actions Workflow**.

---

## ⚡ Các tính năng đã được đồng bộ hóa (100% GHA Parity)

| Tính năng | GitHub Actions (`render_parallel.yml`) | Google Colab (`colab_render_runner.py`) |
|---|---|---|
| **Nạp tài nguyên (Asset Ingestion)** | Tải siêu tốc qua GitHub Release CDN + gdown | Hỗ trợ tham số `--folder-id` tự tải assets về máy Colab |
| **I/O & Bộ nhớ đệm tạm thời** | Dùng ổ đĩa cục bộ của runner | Dùng `/content/temp_render` (ổ đĩa NVMe cục bộ của Colab, tránh nghẽn FUSE) |
| **Độ phân giải & Tốc độ khung hình** | 4K UHD ($3840 \times 2160$) @ 30 FPS | 4K UHD ($3840 \times 2160$) @ 30 FPS |
| **Hiệu ứng "Dim the Lights"** | Đốm lửa fade-in từ 0% lên 100%, không viền oval | Đốm lửa fade-in từ 0% lên 100%, không viền oval |
| **Chốt chặn Human-in-the-loop** | Kiểm tra bắt buộc có Cover (`beat_P01_B01`) | Kiểm tra bắt buộc có Cover (`beat_P01_B01`) |
| **Thư mục Output thống nhất** | `output/chunk_part_*.mp4` & `output/master_*.mp4` | `output/chunk_part_*.mp4` & `output/master_*.mp4` |
| **Kiểm định Gatekeeper GK7** | Bắt buộc thời lượng $\ge 80$ phút, size $> 500$ MB | Bắt buộc thời lượng $\ge 80$ phút, size $> 500$ MB |

---

## 📋 2 Cách Chạy trên Google Colab

### Cách 1: Tải trực tiếp qua Google Drive Folder ID (Không cần mount Drive — Khuyên dùng)
*Mở một Notebook mới trên Google Colab, đổi Runtime sang **T4 GPU**, và chạy 2 ô sau:*

#### Ô 1: Chuẩn bị môi trường (1 phút)
```bash
!git clone https://github.com/triplex2909001/hsnooze.render.git
%cd hsnooze.render
!pip install -q -r requirements.txt
!sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg
```

#### Ô 2: Khởi động Render 4K GPU (Tự động tải assets & xuất video vào `./output`)
```bash
# Thay thế folder ID dự án của bạn (tương tự như input project_folder_id trên GHA):
!python colab_render_runner.py --folder-id "1TILhfJstpKX3stnzIzBk6A8ZZKqc7wtc"
```

---

### Cách 2: Render trực tiếp từ Google Drive Mount
*Nếu bạn đã có sẵn thư mục dự án trong Google Drive:*

```bash
# Ô 1: Mount Drive và chạy
from google.colab import drive
drive.mount('/content/drive')

%cd /content
!git clone https://github.com/triplex2909001/hsnooze.render.git
%cd hsnooze.render
!pip install -q -r requirements.txt

# Ô 2: Chạy render (file tạm sẽ nằm trên SSD cục bộ để tăng tốc tối đa)
!python colab_render_runner.py \
    --project-dir "/content/drive/MyDrive/historysnooze posts/Tên_Thu_Muc_Du_An"
```

---

## 🎯 Các tùy chọn lệnh linh hoạt (CLI Options)

- `--folder-id <ID>`: ID thư mục Google Drive (đồng bộ với `project_folder_id` của GitHub Actions).
- `--parts 1,2,3`: Chỉ render các Part mong muốn (chạy thử nghiệm hoặc render bù).
- `--cpu`: Buộc dùng CPU `libx264` thay vì GPU `h264_nvenc`.
- `--workers 2`: Số lượng FFmpeg worker chạy song song (mặc định: 2 để an toàn cho session NVENC).
- `--force`: Bỏ qua cảnh báo thiếu ảnh Cover nếu muốn render thử nghiệm.
