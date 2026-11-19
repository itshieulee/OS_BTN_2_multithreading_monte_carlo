import csv
import re
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter

def generate(root):
    measurements = root / 'results'
    graphs = measurements
    env = json.loads((measurements / 'environment.json').read_text())
    rows = list(csv.DictReader((measurements / 'summary.csv').open(encoding='utf-8-sig')))
    index = {(r['approach'], int(r['threads']), int(r['k'])): r for r in rows}
    cpu, cfg = env['cpu'], env['config']
    threads = cfg['threads']
    single = float(index[('single', 1, 0)]['mean_seconds'])
    local = [index[('local', t, 0)] for t in threads]
    shared = [index[('shared', t, 1)] for t in threads]
    def save(fig, name):
        fig.tight_layout()
        for ext in ['png', 'svg']:
            fig.savefig(graphs / f'{name}.{ext}', dpi=180, bbox_inches='tight')
            if ext == 'svg':
                svg_path = graphs / f'{name}.svg'
                svg = re.sub(r'<!--.*?-->', '', svg_path.read_text(encoding='utf-8'), flags=re.S)
                svg_path.write_text('\n'.join(s.rstrip() for s in svg.splitlines()) + '\n', encoding='utf-8')
        plt.close(fig)
    def format_threads(ax):
        ax.set_xscale('log', base=2)
        ax.set_xticks(threads)
        ax.xaxis.set_major_formatter(ScalarFormatter())
        for count, label, color in [(cpu['physical_cores'], 'physical cores', '#059669'), (cpu['logical_cpus'], 'logical CPUs', '#8b5cf6')]:
            if count:
                ax.axvline(count, linestyle=':', color=color, label=f'{count} {label}', alpha=.8)
        ax.set_xlabel('Number of threads (log scale)')
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    axes[0].errorbar(threads, [1000*float(r['mean_seconds']) for r in local], yerr=[1000*float(r['sample_sd_seconds']) for r in local], marker='o', capsize=3, color='#1565c0', label='Local accumulation')
    axes[0].set(ylabel='Mean execution time (ms)', title='Measured thread scaling')
    axes[1].plot(threads, [float(r['speedup']) for r in local], 'o-', color='#1565c0', label='Local accumulation')
    axes[1].set(ylabel='Speedup vs single-thread baseline', title='Scaling beyond available cores')
    for ax in axes:
        format_threads(ax)
    fig.suptitle(f"6.2 Thread scaling — N={cfg['points']:,}; {cfg['runs']} runs/config")
    fig.text(.08, .005, 'Time error bars: ±1 sample SD. A decline beyond the CPU count is not assumed.', fontsize=8)
    save(fig, 'section6_thread_scaling')
    fig, ax = plt.subplots(figsize=(9.2, 5.3))
    for source, label, color in [(local, 'Local accumulation', '#1565c0'), (shared, 'Shared mutex (k=1)', '#d45500')]:
        ax.errorbar(threads, [float(r['mean_seconds']) for r in source], yerr=[float(r['sample_sd_seconds']) for r in source], marker='o', capsize=3, label=label, color=color)
    ax.set_yscale('log')
    ax.set(ylabel='Mean execution time (seconds, log scale)', title=f"6.3 Local vs shared counter\nN={cfg['points']:,}; {cfg['runs']} runs/config")
    format_threads(ax)
    fig.text(.13, .005, 'Same point count, RNG, seed policy and timing boundaries. Error bars: ±1 sample SD.', fontsize=8)
    save(fig, 'section6_local_vs_shared')

if __name__ == '__main__':
    generate(Path(__file__).resolve().parents[1])
