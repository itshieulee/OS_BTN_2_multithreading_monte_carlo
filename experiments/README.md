# Experiments

Requirements: Python 3.10+, Matplotlib and GCC with POSIX pthread support for benchmarks.

Run from the repository root:

```bash
python -m pip install -r experiments/requirements.txt
python experiments/generate_figures.py
```

This regenerates all six PNG/SVG figures in `results/` from existing measurements, without rerunning benchmarks.

```bash
python experiments/run.py
python experiments/run.py --resume
```

Edit `config.json` for points, repetitions, threads and k. Use at least five repetitions. Archive previous results before starting a new experiment; `--resume` requires matching configuration, source and environment.

Outputs: raw/summary/tradeoff CSV, metadata, validation, analysis and charts. The Excel workbook is a saved snapshot and is not regenerated.
