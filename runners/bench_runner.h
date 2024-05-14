/*
 * Runner for littlefs benchmarks
 *
 * Copyright (c) 2022, The littlefs authors.
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef BENCH_RUNNER_H
#define BENCH_RUNNER_H


// override LFS_TRACE
void bench_trace(const char *fmt, ...);

#define LFS_TRACE_(fmt, ...) \
    bench_trace("%s:%d:trace: " fmt "%s\n", \
        __FILE__, \
        __LINE__, \
        __VA_ARGS__)
#define LFS_TRACE(...) LFS_TRACE_(__VA_ARGS__, "")
#define LFS_EMUBD_TRACE(...) LFS_TRACE_(__VA_ARGS__, "")

// BENCH_START/BENCH_STOP macros measure readed/proged/erased bytes
// through emubd
void bench_start(const char *meas, uintmax_t iter, uintmax_t size);
void bench_stop(const char *meas);

#define BENCH_START(meas, iter, size) \
    bench_start(meas, iter, size)
#define BENCH_STOP(meas) \
    bench_stop(meas)

// BENCH_RESULT/BENCH_FRESULT allow for explicit non-io measurements
void bench_result(const char *meas, uintmax_t iter, uintmax_t size,
        uintmax_t result);
void bench_fresult(const char *meas, uintmax_t iter, uintmax_t size,
        double result);

#define BENCH_RESULT(meas, iter, size, result) \
    bench_result(meas, iter, size, result)
#define BENCH_FRESULT(meas, iter, size, result) \
    bench_fresult(meas, iter, size, result)


// note these are indirectly included in any generated files
#include "bd/lfs_emubd.h"
#include <stdio.h>

// give source a chance to define feature macros
#undef _FEATURES_H
#undef _STDIO_H


// generated bench configurations
struct lfs_config;

enum bench_flags {
    BENCH_INTERNAL  = 0x1,
};
typedef uint8_t bench_flags_t;

typedef struct bench_define {
    const char *name;
    intmax_t *define;
    intmax_t (*cb)(void *data, size_t i);
    void *data;
    size_t permutations;
} bench_define_t;

struct bench_case {
    const char *name;
    const char *path;
    bench_flags_t flags;

    const bench_define_t *defines;
    size_t permutations;

    bool (*if_)(void);
    void (*run)(struct lfs_config *cfg);
};

struct bench_suite {
    const char *name;
    const char *path;
    bench_flags_t flags;

    const bench_define_t *defines;
    size_t define_count;

    const struct bench_case *cases;
    size_t case_count;
};

extern const struct bench_suite *const bench_suites[];
extern const size_t bench_suite_count;


// deterministic prng for pseudo-randomness in benches
uint32_t bench_prng(uint32_t *state);

#define BENCH_PRNG(state) bench_prng(state)

// generation of specific permutations of an array for exhaustive benching
size_t bench_factorial(size_t x);
void bench_permutation(size_t i, uint32_t *buffer, size_t size);

#define BENCH_FACTORIAL(x) bench_factorial(x)
#define BENCH_PERMUTATION(i, buffer, size) bench_permutation(i, buffer, size)


// a few preconfigured defines that control how benches run
#define BENCH_IMPLICIT_DEFINES \
    /*        name                   value (overridable)                   */ \
    BENCH_DEFINE(READ_SIZE,          1                                      ) \
    BENCH_DEFINE(PROG_SIZE,          1                                      ) \
    BENCH_DEFINE(BLOCK_SIZE,         4096                                   ) \
    BENCH_DEFINE(BLOCK_COUNT,        DISK_SIZE/BLOCK_SIZE                   ) \
    BENCH_DEFINE(DISK_SIZE,          1024*1024                              ) \
    BENCH_DEFINE(RCACHE_SIZE,        lfs_max(16, READ_SIZE)                 ) \
    BENCH_DEFINE(PCACHE_SIZE,        lfs_max(16, PROG_SIZE)                 ) \
    BENCH_DEFINE(FBUFFER_SIZE,       16                                     ) \
    BENCH_DEFINE(LOOKAHEAD_SIZE,     16                                     ) \
    BENCH_DEFINE(INLINE_SIZE,        BLOCK_SIZE/4                           ) \
    BENCH_DEFINE(SHRUB_SIZE,         INLINE_SIZE                            ) \
    BENCH_DEFINE(FRAGMENT_SIZE,      BLOCK_SIZE/8                           ) \
    BENCH_DEFINE(CRYSTAL_THRESH,     BLOCK_SIZE/8                           ) \
    BENCH_DEFINE(BLOCK_CYCLES,       -1                                     ) \
    BENCH_DEFINE(ERASE_VALUE,        0xff                                   ) \
    BENCH_DEFINE(ERASE_CYCLES,       0                                      ) \
    BENCH_DEFINE(BADBLOCK_BEHAVIOR,  LFS_EMUBD_BADBLOCK_PROGERROR           ) \
    BENCH_DEFINE(POWERLOSS_BEHAVIOR, LFS_EMUBD_POWERLOSS_NOOP               )

// declare defines as global intmax_ts
#define BENCH_DEFINE(k, v) \
    extern intmax_t k;

    BENCH_IMPLICIT_DEFINES
#undef BENCH_DEFINE

// map defines to cfg struct fields
#define BENCH_CFG \
    .read_size          = READ_SIZE,            \
    .prog_size          = PROG_SIZE,            \
    .block_size         = BLOCK_SIZE,           \
    .block_count        = BLOCK_COUNT,          \
    .block_cycles       = BLOCK_CYCLES,         \
    .rcache_size        = RCACHE_SIZE,          \
    .pcache_size        = PCACHE_SIZE,          \
    .fbuffer_size       = FBUFFER_SIZE,         \
    .lookahead_size     = LOOKAHEAD_SIZE,       \
    .inline_size        = INLINE_SIZE,          \
    .shrub_size         = SHRUB_SIZE,           \
    .fragment_size      = FRAGMENT_SIZE,        \
    .crystal_thresh     = CRYSTAL_THRESH,

#define BENCH_BDCFG \
    .erase_value        = ERASE_VALUE,          \
    .erase_cycles       = ERASE_CYCLES,         \
    .badblock_behavior  = BADBLOCK_BEHAVIOR,


#endif
