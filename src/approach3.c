/*
 * Approach 3 - Monte Carlo pi with a SHARED counter protected by a mutex.
 *
 * Every thread generates N/T random points. Each time a point falls inside
 * the circle, the thread locks the mutex, increments the global counter,
 * and unlocks. Correct (no race condition) but slow because of lock contention.
 *
 * Build: gcc -O3 -pthread -Wall -Wextra approach3.c -o approach3 -lm
 * Run:   ./approach3 -n 30000000 -t 4 -r 5
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <pthread.h>

/* ---------- shared state ---------- */
static long long       g_count = 0;                       /* shared counter  */
static pthread_mutex_t g_lock  = PTHREAD_MUTEX_INITIALIZER;
static pthread_barrier_t g_start;                         /* common start line */

/* ---------- timing ---------- */
static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/* ---------- independent random generator per thread ---------- */
static uint64_t splitmix64(uint64_t *s) {                 /* builds seeds only */
    uint64_t z = (*s += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}
static inline uint64_t xorshift64s(uint64_t *s) {         /* the generator */
    uint64_t x = *s;
    x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
    *s = x;
    return x * 0x2545F4914F6CDD1DULL;
}
static inline double rnd(uint64_t *s) {                   /* uniform [-1, 1) */
    return ((xorshift64s(s) >> 11) * (1.0 / 9007199254740992.0)) * 2.0 - 1.0;
}
static uint64_t make_seed(uint64_t master, int tid) {
    uint64_t s = master ^ ((uint64_t)(tid + 1) * 0xD1B54A32D192ED03ULL);
    uint64_t v = splitmix64(&s);
    return v ? v : 1;
}

/* ---------- worker ---------- */
typedef struct {
    long long n;        /* points this thread must generate */
    uint64_t  seed;
    double    t_end;    /* when this thread finished        */
} Worker;

static void *worker(void *p) {
    Worker *w = p;
    uint64_t s = w->seed;
    long long n = w->n;

    pthread_barrier_wait(&g_start);          /* wait until everyone is ready */

    for (long long i = 0; i < n; i++) {
        double x = rnd(&s), y = rnd(&s);
        if (x * x + y * y <= 1.0) {
            pthread_mutex_lock(&g_lock);     /* ---- critical section ---- */
            g_count++;
            pthread_mutex_unlock(&g_lock);   /* --------------------------- */
        }
    }

    w->t_end = now();
    return NULL;
}

/* One run: returns elapsed seconds, stores the number of points in the circle. */
static double run_once(long long N, int T, uint64_t seed, long long *inside) {
    /* ---- setup: NOT timed ---- */
    pthread_t *th = malloc(T * sizeof *th);
    Worker    *w  = calloc(T, sizeof *w);
    g_count = 0;                             /* reset before EVERY run */
    pthread_barrier_init(&g_start, NULL, T + 1);

    for (int t = 0; t < T; t++) {
        w[t].n    = N / T + (t == T - 1 ? N % T : 0);   /* remainder -> last thread */
        w[t].seed = make_seed(seed, t);
        pthread_create(&th[t], NULL, worker, &w[t]);
    }

    pthread_barrier_wait(&g_start);          /* release all threads ...   */
    double t0 = now();                       /* ... and start the clock   */

    double t_last = t0;
    for (int t = 0; t < T; t++) {
        pthread_join(th[t], NULL);
        if (w[t].t_end > t_last) t_last = w[t].t_end;
    }

    pthread_barrier_destroy(&g_start);
    *inside = g_count;
    free(th); free(w);
    return t_last - t0;                      /* time until the slowest thread is done */
}

int main(int argc, char **argv) {
    long long N = 30000000LL;
    int T = 4, runs = 5;
    uint64_t seed = 123456789ULL;

    for (int i = 1; i < argc; i++) {
        if      (!strcmp(argv[i], "-n") && i + 1 < argc) N    = atoll(argv[++i]);
        else if (!strcmp(argv[i], "-t") && i + 1 < argc) T    = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-r") && i + 1 < argc) runs = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-s") && i + 1 < argc) seed = strtoull(argv[++i], NULL, 10);
        else { fprintf(stderr, "usage: %s [-n points] [-t threads] [-r runs] [-s seed]\n", argv[0]); return 1; }
    }
    if (T < 1) T = 1;
    if (runs < 1) runs = 1;

    double sum = 0, sum2 = 0;
    for (int r = 0; r < runs; r++) {
        long long inside;
        double t  = run_once(N, T, seed + 99991ULL * r, &inside);   /* new seed each run */
        double pi = 4.0 * inside / N;
        sum += t; sum2 += t * t;
        printf("run %d: time=%.4f s  inside=%lld  pi=%.7f\n", r + 1, t, inside, pi);
    }
    double mean = sum / runs, sd = sqrt(fmax(0.0, sum2 / runs - mean * mean));
    printf("threads=%d points=%lld  mean=%.4f s  sd=%.4f s\n", T, N, mean, sd);
    return 0;
}
