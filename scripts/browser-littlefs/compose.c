/* SPDX-License-Identifier: MIT
 * In-memory UIFlow2 fixture composition. Never formats or runs firmware.
 */
#include "lfs.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static lfs_t fs;
static struct lfs_config config;
static uint8_t *image;
static uint32_t image_size;
static int mounted;

static int range_ok(lfs_block_t block, lfs_off_t off, lfs_size_t size) {
    return block < config.block_count && off <= 4096 && size <= 4096 - off
        && (uint64_t)block * 4096 + off + size <= image_size;
}
static int read_block(const struct lfs_config *c, lfs_block_t block,
                      lfs_off_t off, void *buffer, lfs_size_t size) {
    (void)c;
    if (!range_ok(block, off, size)) return LFS_ERR_INVAL;
    memcpy(buffer, image + block * 4096 + off, size);
    return 0;
}
static int prog_block(const struct lfs_config *c, lfs_block_t block,
                      lfs_off_t off, const void *buffer, lfs_size_t size) {
    (void)c;
    if (!range_ok(block, off, size)) return LFS_ERR_INVAL;
    memcpy(image + block * 4096 + off, buffer, size);
    return 0;
}
static int erase_block(const struct lfs_config *c, lfs_block_t block) {
    (void)c;
    if (!range_ok(block, 0, 4096)) return LFS_ERR_INVAL;
    memset(image + block * 4096, 0xff, 4096);
    return 0;
}
static int sync_block(const struct lfs_config *c) { (void)c; return 0; }

int m5_lfs_mount(uint8_t *buffer, uint32_t size) {
    if (mounted || !buffer || size != 4980736) return LFS_ERR_INVAL;
    image = buffer;
    image_size = size;
    memset(&fs, 0, sizeof(fs));
    memset(&config, 0, sizeof(config));
    config.read = read_block;
    config.prog = prog_block;
    config.erase = erase_block;
    config.sync = sync_block;
    config.read_size = 128;
    config.prog_size = 32;
    config.block_size = 4096;
    config.block_count = size / 4096;
    config.block_cycles = 100;
    config.cache_size = 128;
    config.lookahead_size = 128;
    config.name_max = 255;
    int result = lfs_mount(&fs, &config);
    mounted = result == 0;
    return result;
}

int m5_lfs_unmount(void) {
    if (!mounted) return LFS_ERR_INVAL;
    int result = lfs_unmount(&fs);
    mounted = 0;
    image = NULL;
    image_size = 0;
    return result;
}

int m5_lfs_disk_version(void) {
    if (!mounted) return LFS_ERR_INVAL;
    struct lfs_fsinfo info;
    int result = lfs_fs_stat(&fs, &info);
    return result < 0 ? result : (int)info.disk_version;
}

/* Match uiflow_source._snapshot's directory and file-read ordering before
 * writes. Metadata reads contribute to littlefs's deterministic allocator seed.
 * The final SHA256 remains the authoritative whole-image preservation check.
 */
int m5_lfs_scan(void) {
    if (!mounted) return LFS_ERR_INVAL;
    typedef struct { char path[513]; unsigned depth; } Pending;
    Pending *pending = calloc(4096, sizeof(*pending));
    if (!pending) return LFS_ERR_NOMEM;
    unsigned count = 1, entries = 0, files = 0;
    uint64_t logical_size = 0;
    int result = 0;
    strcpy(pending[0].path, "/");
    while (count) {
        Pending current = pending[--count];
        lfs_dir_t dir;
        result = lfs_dir_open(&fs, &dir, current.path);
        if (result < 0) break;
        struct lfs_info info;
        while ((result = lfs_dir_read(&fs, &dir, &info)) > 0) {
            if (!strcmp(info.name, ".") || !strcmp(info.name, "..")) continue;
            if (++entries > 4096 || !info.name[0] || strchr(info.name, '/')) {
                result = LFS_ERR_INVAL; break;
            }
            char path[513];
            size_t parent = strlen(current.path), name = strlen(info.name);
            int slash = parent > 1;
            if (parent + slash + name >= sizeof(path)) { result = LFS_ERR_INVAL; break; }
            memcpy(path, current.path, parent);
            if (slash) path[parent++] = '/';
            memcpy(path + parent, info.name, name + 1);
            if (info.type == LFS_TYPE_DIR) {
                if (count >= 4096 || current.depth >= 32) { result = LFS_ERR_INVAL; break; }
                strcpy(pending[count].path, path);
                pending[count++].depth = current.depth + 1;
            } else if (info.type == LFS_TYPE_REG) {
                logical_size += info.size;
                if (logical_size > image_size) { result = LFS_ERR_INVAL; break; }
                uint8_t *data = malloc((size_t)info.size + 1);
                if (!data) { result = LFS_ERR_NOMEM; break; }
                lfs_file_t file;
                result = lfs_file_open(&fs, &file, path, LFS_O_RDONLY);
                if (result >= 0) {
                    lfs_ssize_t got = lfs_file_read(&fs, &file, data, info.size + 1);
                    int closed = lfs_file_close(&fs, &file);
                    result = got != (lfs_ssize_t)info.size ? LFS_ERR_CORRUPT : closed;
                }
                free(data);
                if (result < 0) break;
                files++;
            } else { result = LFS_ERR_INVAL; break; }
        }
        int closed = lfs_dir_close(&fs, &dir);
        if (result >= 0) result = closed;
        if (result < 0) break;
    }
    free(pending);
    return result < 0 ? result : (int)files;
}

int m5_lfs_write(const char *path, const uint8_t *data, uint32_t size) {
    if (!mounted || !path || !data || size > 262144
        || (strcmp(path, "/boot.py") && strcmp(path, "/main.py"))) return LFS_ERR_INVAL;
    lfs_file_t file;
    int result = lfs_file_open(&fs, &file, path, LFS_O_WRONLY | LFS_O_CREAT | LFS_O_TRUNC);
    if (result < 0) return result;
    lfs_ssize_t wrote = lfs_file_write(&fs, &file, data, size);
    int closed = lfs_file_close(&fs, &file);
    return wrote != (lfs_ssize_t)size ? LFS_ERR_IO : closed;
}

int m5_lfs_read(const char *path, uint8_t *data, uint32_t capacity) {
    if (!mounted || !path || !data || capacity > 262145) return LFS_ERR_INVAL;
    lfs_file_t file;
    int result = lfs_file_open(&fs, &file, path, LFS_O_RDONLY);
    if (result < 0) return result;
    lfs_ssize_t got = lfs_file_read(&fs, &file, data, capacity);
    int closed = lfs_file_close(&fs, &file);
    return got < 0 ? (int)got : closed < 0 ? closed : (int)got;
}
