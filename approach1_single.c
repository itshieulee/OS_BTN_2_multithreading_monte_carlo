#define _POSIX_C_SOURCE 199309L
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>

static double elapsed_seconds(struct timespec start, struct timespec end) {
    return (double)(end.tv_sec - start.tv_sec) +
           (double)(end.tv_nsec - start.tv_nsec) / 1e9;
}

static inline uint64_t make_seed(uint64_t master_seed, uint64_t thread_id) {
    uint64_t x = master_seed ^ (thread_id * 0x9e3779b97f4a7c15ULL + 1ULL);
    x ^= x >> 30;
    x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27;
    x *= 0x94d049bb133111ebULL;
    x ^= x >> 31;
    return x ? x : 1ULL;
}

static inline uint64_t xorshift64_star(uint64_t *state) {
    uint64_t x = *state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *state = x;
    return x * 0x2545F4914F6CDD1DULL;
}

static inline double rand_minus1_to_1(uint64_t *state) {
    uint64_t r = xorshift64_star(state);
    double u = (double)(r >> 11) * (1.0 / 9007199254740992.0); /* [0.0, 1.0) */
    return u * 2.0 - 1.0;                                     /* [-1.0, 1.0) */
}

static double run_once(uint64_t num_points, uint64_t seed, double *out_seconds) {
    uint64_t state = seed;
    uint64_t inside_circle = 0ULL;

    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);

    for (uint64_t i = 0ULL; i < num_points; ++i) {
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
    const uint64_t num_points = 100000000ULL;
    const uint64_t master_seed = 42ULL;
    const uint64_t seed = make_seed(master_seed, 0ULL);
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
    printf("Points: %" PRIu64 " | Runs: %d | Average time (T_single): %.6f s\n",
           num_points, runs, avg_time);

    return 0;
}