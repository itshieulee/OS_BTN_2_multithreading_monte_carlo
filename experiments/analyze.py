"""Validate repetitions/counters and generate CSV summaries and publication figures."""
import csv
import json
from collections import defaultdict
from pathlib import Path
import statistics as stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results"
LABELS = {"single": "Single-thread baseline", "local": "Local accumulation", "shared": "Shared mutex (k=1)"}
COLORS = {"single": "#64748b", "local": "#1565c0", "shared": "#d45500"}

def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def save(fig, name):
    fig.tight_layout()
    for ext in ["png", "svg"]:
        fig.savefig(OUT / f"{name}.{ext}", dpi=180, bbox_inches="tight")
    plt.close(fig)

def main():
    env = json.loads((OUT / "environment.json").read_text())
    cfg = env["config"]
    raw = list(csv.DictReader((OUT / "raw.csv").open(encoding="utf-8-sig")))
    groups = defaultdict(list)
    for r in raw:
        assert int(r["points"]) == cfg["points"] and int(r["seed"]) == 42
        assert 0 <= int(r["inside"]) <= cfg["points"] and float(r["seconds"]) > 0
        groups[(r["approach"], int(r["threads"]), int(r["k"]))].append(r)
    expected = {("single", 1, 0)}
    expected.update((a, t, 0 if a == "local" else 1) for a in ["local", "shared"] for t in cfg["threads"])
    expected.update(("shared", t, k) for t in cfg["tradeoff_threads"] for k in cfg["batch_sizes"])
    assert set(groups) == expected, "Missing/unexpected configurations"
    for key, rows in groups.items():
        assert len(rows) == cfg["runs"] >= 5, key
        assert {int(r["run"]) for r in rows} == set(range(1, cfg["runs"] + 1)), key
        assert len({int(r["inside"]) for r in rows}) == 1, key
    for t in set(cfg["threads"] + cfg["tradeoff_threads"]):
        counters = {int(r["inside"]) for (a, threads, k), rows in groups.items() if threads == t and a != "single" for r in rows}
        assert len(counters) == 1, f"Local/shared/batch mismatch at {t} threads"
    assert groups[("single", 1, 0)][0]["inside"] == groups[("local", 1, 0)][0]["inside"], "Baseline mismatch"
    baseline = stats.mean(float(r["seconds"]) for r in groups[("single", 1, 0)])
    summary = []
    for (a, t, k), rows in sorted(groups.items()):
        values = [float(r["seconds"]) for r in rows]
        mean, sd = stats.mean(values), stats.stdev(values)
        # 95% t interval for five replicates. Larger run counts use normal approximation, explicitly recorded.
        critical = 2.776445105 if len(values) == 5 else 1.96
        summary.append(dict(approach=a, threads=t, k=k, points=cfg["points"], runs=len(values), mean_seconds=mean, sample_sd_seconds=sd, ci95_halfwidth_seconds=critical*sd/len(values)**0.5, min_seconds=min(values), max_seconds=max(values), speedup=baseline/mean, efficiency=baseline/mean/t, inside=int(rows[0]["inside"]), pi=float(rows[0]["pi"])))
    write_csv(OUT / "summary.csv", summary)
    index = {(r["approach"], r["threads"], r["k"]): r for r in summary}
    trade = []
    for t in cfg["tradeoff_threads"]:
        original = index[("shared", t, 1)]["mean_seconds"]
        for k in cfg["batch_sizes"]:
            r = index[("shared", t, k)]
            trade.append(dict(threads=t, k=k, mean_seconds=r["mean_seconds"], sample_sd_seconds=r["sample_sd_seconds"], speedup_vs_k1=original/r["mean_seconds"], reduction_percent=100*(1-r["mean_seconds"]/original), inside=r["inside"]))
    write_csv(OUT / "tradeoff.csv", trade)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none"})
    threads = cfg["threads"]
    logical, physical = env["cpu"]["logical_cpus"], env["cpu"]["physical_cores"]
    subtitle = f"N={cfg['points']:,}; {cfg['runs']} runs/config; Windows MinGW" if "Windows" in env["platform"] else f"N={cfg['points']:,}; {cfg['runs']} runs/config"
    for field, ylabel, title, filename in [
        ("mean_seconds", "Execution time (seconds, log scale)", "Execution time vs number of threads", "execution_time"),
        ("speedup", "Speedup (baseline mean / parallel mean)", "Speedup vs number of threads", "speedup"),
        ("efficiency", "Parallel efficiency (speedup / threads)", "Parallel efficiency vs number of threads", "efficiency"),
    ]:
        fig, ax = plt.subplots(figsize=(9.2, 5.3))
        for a in ["local", "shared"]:
            rows = [index[(a, t, 0 if a == "local" else 1)] for t in threads]
            if field == "mean_seconds":
                ax.errorbar(threads, [r[field] for r in rows], yerr=[r["sample_sd_seconds"] for r in rows], marker="o", capsize=3, color=COLORS[a], label=LABELS[a])
            else:
                ax.plot(threads, [r[field] for r in rows], "o-", color=COLORS[a], label=LABELS[a])
        # Baseline is measured at one thread; horizontal line is a reference, not additional observations.
        ax.axhline(baseline if field == "mean_seconds" else 1, color=COLORS["single"], linestyle="--", label="Single-thread reference" if field != "efficiency" else "Ideal efficiency")
        ax.scatter([1], [baseline if field == "mean_seconds" else 1], color=COLORS["single"], marker="s", zorder=5)
        if field == "speedup":
            ax.plot(threads, threads, ":", color="#9ca3af", label="Ideal speedup")
        if field in ["mean_seconds", "speedup"]:
            ax.set_yscale("log")
        ax.set_xscale("log", base=2)
        ax.set_xticks(threads)
        ax.xaxis.set_major_formatter(ScalarFormatter())
        ax.axvline(logical, color="#8b5cf6", linestyle=":", alpha=.7, label=f"{logical} logical CPUs")
        ax.set(xlabel="Number of threads (log scale)", ylabel=ylabel, title=title + "\n" + subtitle)
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
        if field == "mean_seconds":
            fig.text(.13, .005, "Error bars: ±1 sample SD. Dashed baseline is measured only at 1 thread.", fontsize=8)
        save(fig, filename)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for t in cfg["tradeoff_threads"]:
        rows = [r for r in trade if r["threads"] == t]
        axes[0].errorbar([r["k"] for r in rows], [r["mean_seconds"] for r in rows], yerr=[r["sample_sd_seconds"] for r in rows], marker="o", capsize=3, label=f"{t} threads")
        axes[1].plot([r["k"] for r in rows], [r["speedup_vs_k1"] for r in rows], "o-", label=f"{t} threads")
    for ax in axes:
        ax.set_xscale("log")
        ax.set_xlabel("Batch size k (iterations, log scale)")
        ax.grid(alpha=.2)
        ax.legend()
    axes[0].set_yscale("log")
    axes[0].set(ylabel="Mean time (seconds, log scale)", title="Shared-counter update frequency")
    axes[1].set(ylabel="Time(k=1) / Time(k)", title="Improvement from batching")
    fig.suptitle("Synchronization trade-off — " + subtitle)
    fig.text(.08, .005, "Time error bars: ±1 sample SD. Batch size counts iterations; empty batches do not lock.", fontsize=8)
    save(fig, "tradeoff")
    best = min((r for r in summary if r["approach"] == "local"), key=lambda r:r["mean_seconds"])
    worst = index[("local", max(threads), 0)]
    report = f'''# Kết quả Experiment & Visualization

## Môi trường và phương pháp

- CPU: {env['cpu']['model']}; {physical} physical cores, {logical} logical CPUs.
- OS: {env['platform']}.
- Compiler: {env['compiler']}; cờ `-O3 -std=c11 -Wall -Wextra -pthread` và `-static` trên Windows; không dùng fast-math.
- Số điểm cố định: {cfg['points']:,}; master seed 42; {cfg['runs']} lần/cấu hình.
- Thread scaling: {threads}. Trade-off tại {cfg['tradeoff_threads']} threads; k={cfg['batch_sizes']}.
- Mỗi phép đo chạy riêng, không chạy benchmark đồng thời. Thứ tự cấu hình được xáo trộn với seed cố định; có warmup không tính vào dữ liệu.
- Adapter gọi trực tiếp hàm tính của code nhóm; bỏ qua main gốc để chuẩn hóa số lần chạy và output độ chính xác 12 chữ số. Không thay thuật toán hay phạm vi timing.
- Baseline đo vòng tính trực tiếp. Parallel đo từ trước start barrier đến sau done barrier và có counter cuối; không gồm cấp phát, tạo/join thread, cleanup, I/O.
- Trung bình và sample SD (n−1); CI95 dùng Student t với df=4 cho 5 lần. Nếu cấu hình >5 lần, script hiện dùng xấp xỉ chuẩn 1.96.
- Speedup = mean(single)/mean(parallel); efficiency = speedup/threads. Biểu đồ time có ±1 sample SD; speedup/efficiency là tỉ số các trung bình, không có khoảng tin cậy.

## Kết quả chính

Baseline trung bình **{baseline:.9f} s**. Local nhanh nhất trong các mức đã đo tại **{best['threads']} threads**, thời gian **{best['mean_seconds']:.9f} s**, speedup **{best['speedup']:.3f}×**, efficiency **{best['efficiency']:.1%}**.

| Approach | Threads | Mean (s) | Sample SD (s) | Speedup | Efficiency |
|---|---:|---:|---:|---:|---:|
'''
    for a in ["single", "local", "shared"]:
        for r in summary:
            if r["approach"] == a and (a != "shared" or r["k"] == 1):
                report += f"| {a} | {r['threads']} | {r['mean_seconds']:.9f} | {r['sample_sd_seconds']:.9f} | {r['speedup']:.3f} | {r['efficiency']:.2%} |\n"
    report += f'''
## Phân tích theo yêu cầu đề

1. **Non-linear speedup:** thread phải chờ start/done, tổng hợp kết quả và được OS lập lịch; phần việc song song không loại bỏ các chi phí này. Hyper-threading không tương đương nhân đôi physical cores. Đối chiếu speedup thực tế trong bảng thay vì giả định tăng tuyến tính.
2. **Saturation:** trong tập cấu hình này local có mean nhỏ nhất ở {best['threads']} threads. Đây là điểm tốt nhất đã đo, chưa chứng minh một ngưỡng tối ưu cho mọi workload; SD và nhiễu hệ thống có thể làm đổi thứ hạng.
3. **Oversubscription:** {max(threads)} threads vượt {logical} logical CPUs. Local tại mức này mất {worst['mean_seconds']:.9f} s, bằng {worst['mean_seconds']/best['mean_seconds']:.2f} lần thời gian mức tốt nhất. Nhiều runnable threads làm tăng cạnh tranh và chi phí lập lịch; không đo trực tiếp context switches nên đây là giải thích cơ chế, không phải số đếm được xác nhận.
4. **Synchronization:** shared k=1 đi qua mutex ở mỗi điểm trúng; critical section dùng chung tạo contention và serialization. So sánh shared/local cùng thread trong summary.csv để định lượng chi phí.
5. **Efficiency:** chia speedup cho số thread. Nếu thêm thread không giảm thời gian tương ứng, efficiency giảm; xem efficiency.png để đối chiếu số liệu thực tế.

## Trade-off: tần suất cập nhật shared counter

Batch tính theo **số iteration**, không theo số điểm trúng. Chỉ lock khi batch có local count >0; k=1 không lock ở iteration trượt. Batch cuối chưa đủ k vẫn được cộng. Counter cuối phải bằng nhau khi thay k.

| Threads | k | Mean (s) | Speedup vs k=1 | Giảm thời gian |
|---:|---:|---:|---:|---:|
'''
    for r in trade:
        report += f"| {r['threads']} | {r['k']} | {r['mean_seconds']:.9f} | {r['speedup_vs_k1']:.2f}× | {r['reduction_percent']:.2f}% |\n"
    local_one = index[("local", 1, 0)]
    detail_t = min(cfg['tradeoff_threads'], key=lambda t:abs(t-logical))
    detail_k = min((k for k in cfg['batch_sizes'] if k > 1), key=lambda k:abs(k-1000))
    report += f'''
### Các điểm cần đọc thận trọng

Local 1 thread có mean {local_one['mean_seconds']:.9f} s, speedup {local_one['speedup']:.3f}× so với baseline. Efficiency có thể vượt 100% ở các mức thread nhỏ trong lượt đo này. Đây là tỉ số thời gian quan sát được giữa hai đường thực thi khác nhau, không chứng minh hiệu năng CPU tăng vượt giới hạn tuyến tính. Vòng tính, vị trí code sau biên dịch, scheduling, tần số CPU và nhiễu nền có thể ảnh hưởng; thực nghiệm này không tách riêng từng nguyên nhân. Một số lần chạy local chỉ kéo dài khoảng vài chục ms nên nhiễu có ảnh hưởng đáng kể. Cần giữ nguyên dữ liệu và công bố SD, không ép efficiency về 100%.

Ở {detail_t} threads, shared k=1 chậm hơn local **{index[('shared', detail_t, 1)]['mean_seconds']/index[('local', detail_t, 0)]['mean_seconds']:.2f}×**. Trong trade-off {detail_t} threads, k={detail_k} nhanh hơn k=1 **{index[('shared', detail_t, 1)]['mean_seconds']/index[('shared', detail_t, detail_k)]['mean_seconds']:.2f}×**. Batch lớn hơn không bắt buộc nhanh hơn; chỉ có thể chọn mức tốt nhất trong các cấu hình đã đo.

Lượt đo hiện tại không chứng minh rằng vượt logical CPU thì thời gian luôn tăng. Nếu mean tại mức thread cao nhất vẫn thấp, cần công bố đúng quan sát đó; không kết luận có suy giảm chỉ từ lý thuyết context switching.

'''
    report += '''
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
'''
    (OUT / "analysis.md").write_text(report, encoding="utf-8")
    (OUT / "validation.json").write_text(json.dumps({"status": "passed", "measurements": len(raw), "configurations": len(groups), "runs_each": cfg["runs"], "counter_checks": "baseline == local(t=1); local == shared for each thread count and k; deterministic across runs"}, indent=2), encoding="utf-8")
    print(f"Validated {len(raw)} measurements / {len(groups)} configurations; charts and analysis generated.")

if __name__ == "__main__":
    main()
