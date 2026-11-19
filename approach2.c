#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define MAX_THREADS 4096
#define BASE_SEED 42u

typedef struct {
    uint64_t samples;
    uint64_t seed;
    uint64_t inside;       /* Written once by this worker. */
} Worker;

static pthread_barrier_t ready, start, done;

/* Wall-clock timing and pthread error handling. */
static double now_seconds(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == -1) {
        perror("clock_gettime");
        exit(EXIT_FAILURE);
    }
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static void check_thread(int rc, const char *operation) {
    if (rc != 0) {
        fprintf(stderr, "%s: %s\n", operation, strerror(rc));
        exit(EXIT_FAILURE);
    }
}

static void meet(pthread_barrier_t *barrier) {
    int rc = pthread_barrier_wait(barrier);
    if (rc != PTHREAD_BARRIER_SERIAL_THREAD)
        check_thread(rc, "pthread_barrier_wait");
}

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

static bool point_is_inside(uint64_t *seed) {
    double x = rnd(seed);
    double y = rnd(seed);
    return x * x + y * y <= 1.0;
}

/* Give each worker its sample count and initial seed. */
static void prepare_worker(Worker *w, unsigned id,
                           unsigned nthreads, uint64_t points) {
    w->samples = points / nthreads;
    if (id == nthreads - 1) w->samples += points % nthreads;
    w->seed = make_seed(BASE_SEED, (int)id);
    w->inside = 0;
}

/* Map: count this worker's hits locally, then publish once. */
static void *worker_main(void *arg) {
    Worker *w = arg;
    uint64_t samples = w->samples;
    uint64_t seed = w->seed;
    uint64_t hits = 0;
    meet(&ready);
    meet(&start);
    for (uint64_t i = 0; i < samples; ++i) {
        if (point_is_inside(&seed)) ++hits;
    }
    w->inside = hits;
    meet(&done);
    return NULL;
}

/* Time sampling and reduction after worker initialization. */
static uint64_t run_parallel(unsigned nthreads, uint64_t points,
                             double *elapsed) {
    pthread_t *threads = calloc(nthreads, sizeof(*threads));
    Worker *workers = calloc(nthreads, sizeof(*workers));
    if (!threads || !workers) {
        perror("calloc");
        exit(EXIT_FAILURE);
    }
    check_thread(pthread_barrier_init(&ready, NULL, nthreads + 1), "ready");
    check_thread(pthread_barrier_init(&start, NULL, nthreads + 1), "start");
    check_thread(pthread_barrier_init(&done, NULL, nthreads + 1), "done");

    for (unsigned i = 0; i < nthreads; ++i) {
        prepare_worker(&workers[i], i, nthreads, points);
        check_thread(pthread_create(&threads[i], NULL, worker_main, &workers[i]),
                     "pthread_create");
    }

    meet(&ready);
    double begin = now_seconds();
    meet(&start);
    meet(&done);
    uint64_t inside = 0;
    /* All workers have published their results by this point. */
    for (unsigned i = 0; i < nthreads; ++i) {
        inside += workers[i].inside;
    }
    *elapsed = now_seconds() - begin;

    for (unsigned i = 0; i < nthreads; ++i)
        check_thread(pthread_join(threads[i], NULL), "pthread_join");
    check_thread(pthread_barrier_destroy(&ready), "destroy ready");
    check_thread(pthread_barrier_destroy(&start), "destroy start");
    check_thread(pthread_barrier_destroy(&done), "destroy done");
    free(workers);
    free(threads);
    return inside;
}

/* Command line: ./approach2 THREADS POINTS */
int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s THREADS POINTS\n", argv[0]);
        return EXIT_FAILURE;
    }
    char *end;
    errno = 0;
    unsigned long nt = strtoul(argv[1], &end, 10);
    if (argv[1][0] < '0' || argv[1][0] > '9' || *end || errno ||
        nt == 0 || nt > MAX_THREADS) {
        fprintf(stderr, "Invalid thread count.\n");
        return EXIT_FAILURE;
    }
    errno = 0;
    uint64_t points = strtoull(argv[2], &end, 10);
    if (argv[2][0] < '0' || argv[2][0] > '9' || *end || errno || !points) {
        fprintf(stderr, "Use a positive point count.\n");
        return EXIT_FAILURE;
    }

    double seconds;
    uint64_t inside = run_parallel((unsigned)nt, points, &seconds);
    /* CSV columns: threads,points,inside,pi,seconds */
    printf("%lu,%" PRIu64 ",%" PRIu64 ",%.9f,%.9f\n",
           nt, points, inside, 4.0 * inside / points, seconds);
    return EXIT_SUCCESS;
}

