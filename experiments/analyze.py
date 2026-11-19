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
    report = f"""# Experiment results

{cfg['points']:,} points; {cfg['runs']} runs/configuration; seed 42. Environment: {env['platform']}, {env['cpu']['model']} ({physical} cores, {logical} logical CPUs).

Baseline mean: {baseline:.6f} s. Fastest measured local configuration: {best['threads']} threads, {best['mean_seconds']:.6f} s, {best['speedup']:.2f}x speedup, {best['efficiency']:.2%} efficiency.

Speedup = baseline mean / parallel mean. Efficiency = speedup / threads. Time error bars show one sample standard deviation.

See raw.csv for individual runs, summary.csv for statistics and tradeoff.csv for batching results. Counters match across local/shared configurations and batch sizes at the same thread count.

Frequent mutex updates serialize counting; batching reduces contention. Short runtimes and background load can affect ratios, including efficiency above 100%. These measurements do not establish a stable saturation point or a slowdown at the highest thread count. No affinity, frequency or context-switch controls were measured.
"""
    (OUT / "analysis.md").write_text(report, encoding="utf-8", newline="\n")
    (OUT / "validation.json").write_text(json.dumps({"status": "passed", "measurements": len(raw), "configurations": len(groups), "runs_each": cfg["runs"], "counter_checks": "baseline == local(t=1); local == shared for each thread count and k; deterministic across runs"}, indent=2), encoding="utf-8")
    print(f"Validated {len(raw)} measurements / {len(groups)} configurations; charts and analysis generated.")

if __name__ == "__main__":
    main()
