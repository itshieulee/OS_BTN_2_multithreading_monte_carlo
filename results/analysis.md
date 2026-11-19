# Experiment results

10,000,000 points; 5 runs/configuration; seed 42. Environment: Windows-11-10.0.26200-SP0, 11th Gen Intel(R) Core(TM) i5-11400H @ 2.70GHz (6 cores, 12 logical CPUs).

Baseline mean: 0.093262 s. Fastest measured local configuration: 100 threads, 0.011181 s, 8.34x speedup, 8.34% efficiency.

Speedup = baseline mean / parallel mean. Efficiency = speedup / threads. Time error bars show one sample standard deviation.

See raw.csv for individual runs, summary.csv for statistics and tradeoff.csv for batching results. Counters match across local/shared configurations and batch sizes at the same thread count.

Frequent mutex updates serialize counting; batching reduces contention. Short runtimes and background load can affect ratios, including efficiency above 100%. These measurements do not establish a stable saturation point or a slowdown at the highest thread count. No affinity, frequency or context-switch controls were measured.
