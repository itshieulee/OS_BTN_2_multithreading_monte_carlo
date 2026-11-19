#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define MASTER_SEED 42ULL
#define DEFAULT_POINTS 100000000ULL
#define MAX_THREADS 4096
#define MAX_RUNS 1000000

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    bool go;
    bool abort;
} Gate;

typedef struct {
    Gate *gate;
    uint64_t n;
    uint64_t k;
    uint64_t seed;
} Worker;

static pthread_barrier_t ready, start, done;
static uint64_t g_count;
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;

static double now(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
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

static uint64_t splitmix64(uint64_t *s) {
    uint64_t z = (*s += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

static inline uint64_t xorshift64s(uint64_t *s) {
    uint64_t x = *s;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *s = x;
    return x * 0x2545F4914F6CDD1DULL;
}

static inline double rnd(uint64_t *s) {
    return ((xorshift64s(s) >> 11) * (1.0 / 9007199254740992.0)) * 2.0 - 1.0;
}

static uint64_t make_seed(uint64_t master, int tid) {
    uint64_t s = master ^ ((uint64_t)(tid + 1) * 0xD1B54A32D192ED03ULL);
    uint64_t v = splitmix64(&s);
    return v ? v : 1;
}

static int gate_init(Gate *g) {
    int rc = pthread_mutex_init(&g->mutex, NULL);
    if (rc) return rc;
    rc = pthread_cond_init(&g->cond, NULL);
    if (rc) {
        pthread_mutex_destroy(&g->mutex);
        return rc;
    }
    g->go = false;
    g->abort = false;
    return 0;
}

static void gate_destroy(Gate *g) {
    pthread_cond_destroy(&g->cond);
    pthread_mutex_destroy(&g->mutex);
}

static bool gate_wait(Gate *g) {
    pthread_mutex_lock(&g->mutex);
    while (!g->go && !g->abort) pthread_cond_wait(&g->cond, &g->mutex);
    bool go = g->go;
    pthread_mutex_unlock(&g->mutex);
    return go;
}

/* Untimed launch guard: abort safely if only some threads were created. */
static void gate_release(Gate *g) {
    pthread_mutex_lock(&g->mutex);
    g->go = true;
    pthread_cond_broadcast(&g->cond);
    pthread_mutex_unlock(&g->mutex);
}

static void gate_abort(Gate *g) {
    pthread_mutex_lock(&g->mutex);
    g->abort = true;
    pthread_cond_broadcast(&g->cond);
    pthread_mutex_unlock(&g->mutex);
}

static void *worker(void *arg) {
    Worker *w = arg;
    uint64_t s = w->seed, n = w->n, k = w->k, left = k, local = 0;

    if (!gate_wait(w->gate)) return NULL;
    meet(&ready);
    meet(&start);

    for (uint64_t i = 0; i < n; i++) {
        double x = rnd(&s), y = rnd(&s);
        if (x * x + y * y <= 1.0) local++;
        if (--left == 0) {
            left = k;
            if (local) {
                pthread_mutex_lock(&g_lock);
                g_count += local;
                pthread_mutex_unlock(&g_lock);
                local = 0;
            }
        }
    }

    if (local) {
        pthread_mutex_lock(&g_lock);
        g_count += local;
        pthread_mutex_unlock(&g_lock);
    }

    meet(&done);
    return NULL;
}

static int run_once(uint64_t N, unsigned T, uint64_t k,
                    uint64_t *inside, double *elapsed) {
    pthread_t *th = calloc(T, sizeof *th);
    Worker *w = calloc(T, sizeof *w);
    if (!th || !w) {
        perror("calloc");
        free(th);
        free(w);
        return -1;
    }

    Gate gate;
    int rc = gate_init(&gate);
    if (rc) {
        fprintf(stderr, "gate_init: %s\n", strerror(rc));
        free(th);
        free(w);
        return -1;
    }

    check_thread(pthread_barrier_init(&ready, NULL, T + 1), "init ready");
    check_thread(pthread_barrier_init(&start, NULL, T + 1), "init start");
    check_thread(pthread_barrier_init(&done, NULL, T + 1), "init done");

    g_count = 0;
    uint64_t base = N / T, rest = N % T;
    unsigned created = 0;
    for (unsigned t = 0; t < T; t++) {
        w[t].gate = &gate;
        w[t].n = base + (t == T - 1 ? rest : 0);
        w[t].k = k;
        w[t].seed = make_seed(MASTER_SEED, (int)t);
        rc = pthread_create(&th[t], NULL, worker, &w[t]);
        if (rc) {
            fprintf(stderr, "pthread_create: %s\n", strerror(rc));
            break;
        }
        created++;
    }

    if (created < T) {
        gate_abort(&gate);
        for (unsigned t = 0; t < created; t++) pthread_join(th[t], NULL);
        check_thread(pthread_barrier_destroy(&ready), "destroy ready");
        check_thread(pthread_barrier_destroy(&start), "destroy start");
        check_thread(pthread_barrier_destroy(&done), "destroy done");
        gate_destroy(&gate);
        free(th);
        free(w);
        return -1;
    }

    /* Same timing boundaries as Approach 2: setup and joins are excluded. */
    gate_release(&gate);
    meet(&ready);
    double t0 = now();
    meet(&start);
    meet(&done);
    *inside = g_count;
    *elapsed = now() - t0;

    for (unsigned t = 0; t < T; t++)
        check_thread(pthread_join(th[t], NULL), "pthread_join");

    check_thread(pthread_barrier_destroy(&ready), "destroy ready");
    check_thread(pthread_barrier_destroy(&start), "destroy start");
    check_thread(pthread_barrier_destroy(&done), "destroy done");
    gate_destroy(&gate);
    free(th);
    free(w);
    return 0;
}

static bool parse_u64(const char *s, uint64_t max, uint64_t *out) {
    if (s[0] < '0' || s[0] > '9') return false;
    char *end;
    errno = 0;
    unsigned long long v = strtoull(s, &end, 10);
    if (*end || errno || v == 0 || v > max) return false;
    *out = v;
    return true;
}

int main(int argc, char **argv) {
    uint64_t N = DEFAULT_POINTS, T = 4, runs = 5, k = 1;

    for (int i = 1; i < argc; i++) {
        uint64_t *dst, max;
        const char *name;
        if (!strcmp(argv[i], "-n")) { dst = &N; max = UINT64_MAX; name = "points"; }
        else if (!strcmp(argv[i], "-t")) { dst = &T; max = MAX_THREADS; name = "threads"; }
        else if (!strcmp(argv[i], "-r")) { dst = &runs; max = MAX_RUNS; name = "runs"; }
        else if (!strcmp(argv[i], "-k")) { dst = &k; max = UINT64_MAX; name = "k"; }
        else {
            fprintf(stderr, "usage: %s [-n points] [-t threads] [-r runs] [-k batch]\n", argv[0]);
            return EXIT_FAILURE;
        }
        if (i + 1 >= argc || !parse_u64(argv[++i], max, dst)) {
            fprintf(stderr, "%s must be a positive integer up to %" PRIu64 "\n", name, max);
            return EXIT_FAILURE;
        }
    }

    double sum = 0, sum2 = 0;
    uint64_t first = 0;
    bool same = true;
    for (uint64_t r = 0; r < runs; r++) {
        uint64_t inside;
        double t;
        if (run_once(N, (unsigned)T, k, &inside, &t) != 0) return EXIT_FAILURE;
        if (r == 0) first = inside;
        else if (inside != first) same = false;
        sum += t;
        sum2 += t * t;
        printf("run %" PRIu64 ": time=%.4f s  inside=%" PRIu64 "  pi=%.7f\n",
               r + 1, t, inside, 4.0 * (double)inside / (double)N);
    }

    double mean = sum / (double)runs;
    double sd = sqrt(fmax(0.0, sum2 / (double)runs - mean * mean));
    printf("threads=%u points=%" PRIu64 " k=%" PRIu64 "  mean=%.4f s  sd=%.4f s\n",
           (unsigned)T, N, k, mean, sd);

    if (!same) {
        fprintf(stderr, "hit count differs between runs\n");
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
