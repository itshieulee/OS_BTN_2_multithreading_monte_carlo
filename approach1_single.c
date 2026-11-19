#define _POSIX_C_SOURCE 199309L
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static double elapsed_seconds(struct timespec start, struct timespec end) {
    return (double)(end.tv_sec - start.tv_sec) +
           (double)(end.tv_nsec - start.tv_nsec) / 1e9;
}

static inline unsigned long long next_u64(unsigned long long *state) {
    *state = (*state) * 6364136223846793005ULL + 1442695040888963407ULL;
    return *state;
}

static inline double rand_minus1_to_1(unsigned long long *state) {
    unsigned long long r = next_u64(state);
    double u = (double)(r >> 11) * (1.0 / 9007199254740992.0); /* [0, 1) */
    return u * 2.0 - 1.0;
}

static double run_once(long long num_points, unsigned long long seed, double *out_seconds) {
    unsigned long long state = seed;
    long long inside_circle = 0;

    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);

    for (long long i = 0; i < num_points; ++i) {
        double x = rand_minus1_to_1(&state);
        double y = rand_minus1_to_1(&state);
        if (x * x + y * y <= 1.0) {
            ++inside_circle;
        }
    }

    clock_gettime(CLOCK_MONOTONIC, &end);
    *out_seconds = elapsed_seconds(start, end);

    return 4.0 * (double)inside_circle / (double)num_points;
}

int main(void) {
    const long long num_points = 100000000LL;
    const unsigned long long seed = 42ULL;
    const int runs = 5;

    double total_time = 0.0;
    double pi_estimate = 0.0;

    for (int r = 1; r <= runs; ++r) {
        double sec = 0.0;
        pi_estimate = run_once(num_points, seed, &sec);
        total_time += sec;
        printf("Run %d: time = %.6f s, pi = %.8f\n", r, sec, pi_estimate);
    }

    double avg_time = total_time / (double)runs;
    printf("Points: %lld | Runs: %d | Average time (T_single): %.6f s\n",
           num_points, runs, avg_time);

    return 0;
}