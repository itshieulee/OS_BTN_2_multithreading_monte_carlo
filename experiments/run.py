"""Build adapters around the group's actual run_once functions and collect real timings."""
import argparse
import csv
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "single": ("approach1_single.c", "58594d8f5fcbaa36a0af65067f1f13ef97de0495"),
    "local": ("approach2.c", "c4b5fc986a6aa37ea76587eff81bd34a641c8919"),
    "shared": ("src/approach3.c", "de068d05c30cb1c94fa4ccbbd06126470f46209a"),
}
FIELDS = ["sequence", "timestamp_utc", "approach", "points", "threads", "k", "seed", "run", "inside", "pi", "seconds"]

def cpu_info():
    info = {"logical_cpus": os.cpu_count(), "physical_cores": None, "model": platform.processor()}
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            info["model"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        size = ctypes.c_ulong(0)
        fn = ctypes.windll.kernel32.GetLogicalProcessorInformationEx
        fn(0, None, ctypes.byref(size))  # RelationProcessorCore
        buf = ctypes.create_string_buffer(size.value)
        if fn(0, buf, ctypes.byref(size)):
            offset, cores = 0, 0
            while offset < size.value:
                relation = ctypes.c_ulong.from_buffer(buf, offset).value
                length = ctypes.c_ulong.from_buffer(buf, offset + 4).value
                if not length:
                    break
                cores += relation == 0
                offset += length
            info["physical_cores"] = cores
    return info

def build(cc):
    build_dir = ROOT / "experiments" / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    flags = ["-O3", "-std=c11", "-Wall", "-Wextra", "-pthread"]
    if os.name == "nt":
        flags += ["-static"]  # Avoid dependence on a system PATH pthread DLL.
    binaries = {}
    commands = []
    for name, (source, _) in SOURCES.items():
        if name == "single":
            call = "double pi = run_once(n, make_seed(42, 0), &seconds); inside = (uint64_t)(pi * (double)n / 4.0 + 0.5);"
        elif name == "local":
            call = "inside = run_parallel(t, n, &seconds);"
        else:
            call = "if (run_once(n, t, k, &inside, &seconds) != 0) return 1;"
        adapter = f'''#define main original_program_main
#include "{(ROOT / source).as_posix()}"
#undef main
#include <stdlib.h>
int main(int argc, char **argv) {{
    if (argc != 4) return 1;
    uint64_t n = strtoull(argv[1], NULL, 10);
    unsigned t = (unsigned)strtoul(argv[2], NULL, 10);
    uint64_t k = strtoull(argv[3], NULL, 10);
    (void)t; (void)k;
    uint64_t inside;
    double seconds;
    {call}
    printf("%" PRIu64 ",%.12f,%.12f\\n", inside, 4.0 * (double)inside / (double)n, seconds);
    return 0;
}}
'''
        path = build_dir / f"{name}_adapter.c"
        path.write_text(adapter, encoding="utf-8")
        binary = build_dir / (name + (".exe" if os.name == "nt" else ""))
        command = [cc, *flags, str(path), "-o", str(binary), "-lm"]
        subprocess.run(command, check=True, capture_output=True, text=True)
        commands.append(command)
        binaries[name] = binary
    return binaries, commands

def measure(binary, n, t, k, timeout):
    result = subprocess.run([str(binary), str(n), str(t), str(k)], check=True, capture_output=True, text=True, timeout=timeout)
    inside, pi, seconds = result.stdout.strip().split(",")
    inside, pi, seconds = int(inside), float(pi), float(seconds)
    if not (0 <= inside <= n and seconds > 0 and abs(pi - 4 * inside / n) < 1e-10):
        raise ValueError(f"Invalid measurement: {result.stdout}")
    return inside, pi, seconds

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "experiments" / "config.json")
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    if cfg["runs"] < 5 or not 0 < cfg["points"] <= 2**53:
        raise ValueError("Use at least 5 runs and 0 < points <= 2^53")
    if cfg["master_seed"] != 42 or any(t < 1 or t > 4096 for t in cfg["threads"] + cfg["tradeoff_threads"]) or any(k < 1 for k in cfg["batch_sizes"]):
        raise ValueError("Invalid seed, threads, or batch size")
    if 1 not in cfg['threads'] or not set(cfg['tradeoff_threads']) <= set(cfg['threads']) or 1 not in cfg['batch_sizes'] or not any(k > 1 for k in cfg['batch_sizes']):
        raise ValueError('Include 1 thread, tradeoff threads in scaling, and k=1 plus k>1')
    binaries, commands = build(args.cc)
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    metadata = {"platform": platform.platform(), "cpu": cpu_info(), "compiler": subprocess.check_output([args.cc, "--version"], text=True).splitlines()[0], "commands": commands, "config": cfg, "sources": {name: {"path": path, "commit": sha, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()} for name, (path, sha) in SOURCES.items()}, "timing": "Source run_once/run_parallel wall-clock intervals. Parallel: ready, t0, start, done, final count, t1; excludes allocation, creation, join and I/O. Single: sampling loop only.", "baseline_adapter": "Single inside recovered by rounding pi*N/4; N restricted to <= 2^53.", "started_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    raw = out / "raw.csv"
    if raw.exists() and not args.resume:
        raise FileExistsError("Results exist. Use --resume for this run, or choose a new output copy.")
    if args.resume:
        previous = json.loads((out / "environment.json").read_text())
        for key in ["platform", "cpu", "compiler", "config", "sources"]:
            if previous[key] != metadata[key]:
                raise ValueError(f"Resume mismatch: {key}")
        metadata = previous
    (out / "environment.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    configs = {("single", 1, 0)}
    configs.update((name, t, 0 if name == "local" else 1) for name in ["local", "shared"] for t in cfg["threads"])
    configs.update(("shared", t, k) for t in cfg["tradeoff_threads"] for k in cfg["batch_sizes"])
    jobs = [(name, t, k, run) for name, t, k in sorted(configs) for run in range(1, cfg["runs"] + 1)]
    random.Random(cfg["schedule_seed"]).shuffle(jobs)
    existing = list(csv.DictReader(raw.open(encoding="utf-8-sig"))) if raw.exists() else []
    done = {(r["approach"], int(r["threads"]), int(r["k"]), int(r["run"])) for r in existing}
    if len(done) != len(existing):
        raise ValueError("Duplicate measurements in CSV")
    # Warm up each executable once; warmups are excluded from measurements.
    for binary in binaries.values():
        measure(binary, 100000, 1, 1, cfg["timeout_seconds"])
    with raw.open("a" if existing else "w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        if not existing:
            writer.writeheader()
        sequence = len(existing)
        for job in jobs:
            if job in done:
                continue
            name, t, k, run = job
            inside, pi, seconds = measure(binaries[name], cfg["points"], t, max(k, 1), cfg["timeout_seconds"])
            sequence += 1
            writer.writerow(dict(sequence=sequence, timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat(), approach=name, points=cfg["points"], threads=t, k=k, seed=42, run=run, inside=inside, pi=f"{pi:.12f}", seconds=f"{seconds:.12f}"))
            stream.flush()
            print(f"{sequence}/{len(jobs)} {name} threads={t} k={k} run={run}: {seconds:.6f}s", flush=True)
    metadata["completed_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    (out / "environment.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "experiments" / "analyze.py")], check=True)

if __name__ == "__main__":
    main()
