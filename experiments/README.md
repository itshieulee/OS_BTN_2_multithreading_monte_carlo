# Experiment & Visualization — Thành viên 4

## Chạy lại

Yêu cầu Python 3.10+, Matplotlib và GCC có POSIX pthread/barrier (Linux hoặc MinGW-w64 POSIX trên Windows).

```bash
python -m pip install -r experiments/requirements.txt
python experiments/run.py
```

`config.json` đặt N, số lần chạy, các mức thread và k. Hiện dùng N=10^7, 5 lần/cấu hình, threads=1,2,4,6,12,24,100. Trade-off k=1,10,100,1000,10000 tại 6 và 12 threads.

Nếu đang chạy bị ngắt, dùng `python experiments/run.py --resume`; script chỉ tiếp tục khi môi trường/compiler/config/source hash khớp. Để tạo một experiment mới, sao chép project sang thư mục mới rồi chuyển bộ results cũ đi trước khi chạy. Không trộn dữ liệu của các lần experiment khác nhau.

Chỉ tổng hợp/vẽ lại từ raw hiện có:

```bash
python experiments/analyze.py
```

## Cách thu dữ liệu

Script tạo các adapter trong `experiments/build/`, include nguồn gốc và gọi trực tiếp hàm `run_once`/`run_parallel`. Main gốc được đổi tên, vì ba chương trình có giao diện CLI khác nhau. Baseline vẫn chạy đúng vòng tính của Approach 1. Adapter chuẩn hóa N và xuất thời gian với 12 chữ số thập phân; không dùng thời gian khởi động process làm execution time.

Baseline trả pi thay vì inside, nên adapter phục hồi inside bằng round(pi*N/4), với N giới hạn <=2^53. Cấu hình thực tế N=10^7 nằm rất xa giới hạn này. Parallel trả inside trực tiếp. Các file nguồn là snapshot tại commit ghi trong `results/environment.json`; RNG/seed và thuật toán không bị thay bởi adapter.

Warmup mỗi executable một lần, không đưa vào raw. Các job chạy tuần tự theo thứ tự xáo trộn seed cố định, mỗi job là một process riêng. Seed Monte Carlo vẫn cố định 42. Tránh tải CPU nặng khi chạy lại; không mở nhiều lượt benchmark đồng thời.

## Phạm vi timing

- Single: seed/counter chuẩn bị trước timer; đo vòng sinh và đếm điểm; tính pi/printf ở ngoài.
- Local/shared: worker sẵn sàng ở ready; main lấy t0, thả start; qua done, có counter cuối rồi lấy t1. Bao gồm chi phí start/done và reduction cần thiết; loại allocation, thread creation/join, cleanup và I/O.
- Shared giữ launch guard ở ngoài timing để hủy an toàn khi tạo thiếu thread.

## Dữ liệu và biểu đồ

- `results/raw.csv`: mỗi dòng là một lần đo, có timestamp, sequence, approach, N, threads, k, seed, run, inside, pi, seconds. k=0 nghĩa không áp dụng cho single/local.
- `summary.csv`: mean, sample SD, CI95, min/max, speedup, efficiency. Các CSV có UTF-8 BOM để mở trong Excel.
- `tradeoff.csv`: tỉ số mean(k=1)/mean(k) và phần trăm giảm thời gian.
- `measurements.xlsx`: dữ liệu Excel gồm Summary và Raw; speedup/efficiency được tính bằng công thức. Đây là bản đóng gói của lượt đo hiện tại, không được tự ghi lại bởi analyze.py; CSV là nguồn chuẩn khi chạy lượt mới.
- `execution_time`, `speedup`, `efficiency`, `tradeoff`: PNG để chèn báo cáo và SVG để phóng to/chỉnh sửa. Ảnh được vẽ bằng Matplotlib từ CSV, không phải ảnh AI hay số liệu minh họa.
- `analysis.md`: kết quả và phân tích tiếng Việt; `validation.json`: số cấu hình/lần đo và kiểm tra counter.

Trục thread dùng log; time và speedup dùng log y, efficiency dùng linear y. Baseline được đo tại một thread; đường baseline ngang là đường tham chiếu, không phải đo single ở mọi thread. Thanh sai số time là ±1 sample SD, không phải CI95. Điểm trên đồ thị là số liệu đo; đường nối chỉ giúp đọc xu hướng.

## Nguồn

Repo: https://github.com/itshieulee/OS_BTN_2_multithreading_monte_carlo

Snapshot Approach 1: 58594d8; Approach 2: c4b5fc9; Approach 3: de068d0. Snapshot tích hợp chỉ phục vụ tái lập thực nghiệm, không sửa các branch thành viên khác. Chưa dùng kết quả repo tham khảo làm dữ liệu của nhóm.
