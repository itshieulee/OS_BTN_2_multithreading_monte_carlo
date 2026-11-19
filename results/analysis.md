# Kết quả Experiment & Visualization

## Môi trường và phương pháp

- CPU: 11th Gen Intel(R) Core(TM) i5-11400H @ 2.70GHz; 6 physical cores, 12 logical CPUs.
- OS: Windows-11-10.0.26200-SP0.
- Compiler: gcc (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r8) 13.2.0; cờ `-O3 -std=c11 -Wall -Wextra -pthread` và `-static` trên Windows; không dùng fast-math.
- Số điểm cố định: 10,000,000; master seed 42; 5 lần/cấu hình.
- Thread scaling: [1, 2, 4, 6, 12, 24, 100]. Trade-off tại [6, 12] threads; k=[1, 10, 100, 1000, 10000].
- Mỗi phép đo chạy riêng, không chạy benchmark đồng thời. Thứ tự cấu hình được xáo trộn với seed cố định; có warmup không tính vào dữ liệu.
- Adapter gọi trực tiếp hàm tính của code nhóm; bỏ qua main gốc để chuẩn hóa số lần chạy và output độ chính xác 12 chữ số. Không thay thuật toán hay phạm vi timing.
- Baseline đo vòng tính trực tiếp. Parallel đo từ trước start barrier đến sau done barrier và có counter cuối; không gồm cấp phát, tạo/join thread, cleanup, I/O.
- Trung bình và sample SD (n−1); CI95 dùng Student t với df=4 cho 5 lần. Nếu cấu hình >5 lần, script hiện dùng xấp xỉ chuẩn 1.96.
- Speedup = mean(single)/mean(parallel); efficiency = speedup/threads. Biểu đồ time có ±1 sample SD; speedup/efficiency là tỉ số các trung bình, không có khoảng tin cậy.

## Kết quả chính

Baseline trung bình **0.093262240 s**. Local nhanh nhất trong các mức đã đo tại **100 threads**, thời gian **0.011180940 s**, speedup **8.341×**, efficiency **8.3%**.

| Approach | Threads | Mean (s) | Sample SD (s) | Speedup | Efficiency |
|---|---:|---:|---:|---:|---:|
| single | 1 | 0.093262240 | 0.014927383 | 1.000 | 100.00% |
| local | 1 | 0.085029180 | 0.013999290 | 1.097 | 109.68% |
| local | 2 | 0.040757180 | 0.005355368 | 2.288 | 114.41% |
| local | 4 | 0.028675540 | 0.006922611 | 3.252 | 81.31% |
| local | 6 | 0.022813880 | 0.005548331 | 4.088 | 68.13% |
| local | 12 | 0.014197240 | 0.002413618 | 6.569 | 54.74% |
| local | 24 | 0.014563620 | 0.002275437 | 6.404 | 26.68% |
| local | 100 | 0.011180940 | 0.000708779 | 8.341 | 8.34% |
| shared | 1 | 0.467197600 | 0.052040666 | 0.200 | 19.96% |
| shared | 2 | 0.609211560 | 0.038826843 | 0.153 | 7.65% |
| shared | 4 | 0.719186420 | 0.071779110 | 0.130 | 3.24% |
| shared | 6 | 1.137773040 | 0.037320281 | 0.082 | 1.37% |
| shared | 12 | 1.361811920 | 0.043413900 | 0.068 | 0.57% |
| shared | 24 | 1.337134780 | 0.032490221 | 0.070 | 0.29% |
| shared | 100 | 1.354836660 | 0.016840240 | 0.069 | 0.07% |

## Phân tích theo yêu cầu đề

1. **Non-linear speedup:** thread phải chờ start/done, tổng hợp kết quả và được OS lập lịch; phần việc song song không loại bỏ các chi phí này. Hyper-threading không tương đương nhân đôi physical cores. Đối chiếu speedup thực tế trong bảng thay vì giả định tăng tuyến tính.
2. **Saturation:** trong tập cấu hình này local có mean nhỏ nhất ở 100 threads. Đây là điểm tốt nhất đã đo, chưa chứng minh một ngưỡng tối ưu cho mọi workload; SD và nhiễu hệ thống có thể làm đổi thứ hạng.
3. **Oversubscription:** 100 threads vượt 12 logical CPUs. Local tại mức này mất 0.011180940 s, bằng 1.00 lần thời gian mức tốt nhất. Nhiều runnable threads làm tăng cạnh tranh và chi phí lập lịch; không đo trực tiếp context switches nên đây là giải thích cơ chế, không phải số đếm được xác nhận.
4. **Synchronization:** shared k=1 đi qua mutex ở mỗi điểm trúng; critical section dùng chung tạo contention và serialization. So sánh shared/local cùng thread trong summary.csv để định lượng chi phí.
5. **Efficiency:** chia speedup cho số thread. Nếu thêm thread không giảm thời gian tương ứng, efficiency giảm; xem efficiency.png để đối chiếu số liệu thực tế.

## Trade-off: tần suất cập nhật shared counter

Batch tính theo **số iteration**, không theo số điểm trúng. Chỉ lock khi batch có local count >0; k=1 không lock ở iteration trượt. Batch cuối chưa đủ k vẫn được cộng. Counter cuối phải bằng nhau khi thay k.

| Threads | k | Mean (s) | Speedup vs k=1 | Giảm thời gian |
|---:|---:|---:|---:|---:|
| 6 | 1 | 1.137773040 | 1.00× | 0.00% |
| 6 | 10 | 0.274870100 | 4.14× | 75.84% |
| 6 | 100 | 0.044883000 | 25.35× | 96.06% |
| 6 | 1000 | 0.021423060 | 53.11× | 98.12% |
| 6 | 10000 | 0.024645680 | 46.17× | 97.83% |
| 12 | 1 | 1.361811920 | 1.00× | 0.00% |
| 12 | 10 | 0.307628740 | 4.43× | 77.41% |
| 12 | 100 | 0.045789800 | 29.74× | 96.64% |
| 12 | 1000 | 0.013750500 | 99.04× | 98.99% |
| 12 | 10000 | 0.016205700 | 84.03× | 98.81% |

### Các điểm cần đọc thận trọng

Local 1 thread có mean 0.085029180 s, speedup 1.097× so với baseline. Efficiency có thể vượt 100% ở các mức thread nhỏ trong lượt đo này. Đây là tỉ số thời gian quan sát được giữa hai đường thực thi khác nhau, không chứng minh hiệu năng CPU tăng vượt giới hạn tuyến tính. Vòng tính, vị trí code sau biên dịch, scheduling, tần số CPU và nhiễu nền có thể ảnh hưởng; thực nghiệm này không tách riêng từng nguyên nhân. Một số lần chạy local chỉ kéo dài khoảng vài chục ms nên nhiễu có ảnh hưởng đáng kể. Cần giữ nguyên dữ liệu và công bố SD, không ép efficiency về 100%.

Ở 12 threads, shared k=1 chậm hơn local **95.92×**. Trong trade-off 12 threads, k=1000 nhanh hơn k=1 **99.04×**. Batch lớn hơn không bắt buộc nhanh hơn; chỉ có thể chọn mức tốt nhất trong các cấu hình đã đo.

Lượt đo hiện tại không chứng minh rằng vượt logical CPU thì thời gian luôn tăng. Nếu mean tại mức thread cao nhất vẫn thấp, cần công bố đúng quan sát đó; không kết luận có suy giảm chỉ từ lý thuyết context switching.


Batch lớn giảm số lần vào critical section nhưng counter chung được cập nhật thưa hơn. Đề chỉ đọc kết quả cuối nên không mất độ chính xác; nếu cần quan sát tiến độ tức thời, counter có thể chậm phản ánh tối đa k−1 iteration mỗi worker trước lần flush kế tiếp. Không có yêu cầu tiến độ trực tiếp thì local accumulation thường tránh contention tốt hơn.

## Kiểm tra tính đúng và giới hạn

- Đã kiểm tra đủ cấu hình, không trùng run và mỗi cấu hình có ít nhất 5 lần; counter tái lập giữa các lần.
- Cùng N/threads: local và shared có cùng inside; mọi k có cùng inside. Baseline và local 1 thread cũng có cùng inside.
- Bộ sinh RNG/seed cùng nhau; các thread count khác nhau dùng phân hoạch và stream khác nhau nên không yêu cầu inside bằng nhau giữa các số thread.
- Đây là thực nghiệm trên máy Windows đang sử dụng, không phải Linux hoặc môi trường CPU độc quyền. Không khóa affinity/tần số, không thu nhiệt độ, power state hay context switches. Không loại bỏ outlier. Kết quả không bảo đảm tái lập tuyệt đối trên máy khác.
- Chỉ kết luận theo các thread/k đã chạy. Không suy diễn dữ liệu chưa đo từ đường nối trên biểu đồ.

## Best practices

Giữ counter và RNG state riêng trong vòng tính; tổng hợp sau khi worker hoàn thành. Khi bắt buộc dùng shared state, gom cập nhật theo batch. Chọn số thread bằng thực nghiệm trên CPU mục tiêu; giữ input, compiler flags và timing boundaries nhất quán. Luôn lưu từng lần chạy và độ biến thiên thay vì chỉ công bố một thời gian.

## Sản phẩm

`raw.csv`: từng lần đo; `summary.csv`: thống kê/time/speedup/efficiency; `tradeoff.csv`: so sánh k; `environment.json`: môi trường, commit và SHA256 nguồn. `execution_time`, `speedup`, `efficiency`, `tradeoff` có cả PNG và SVG.
