#include <dirent.h>
#include <stdio.h>
#include <string.h>
#include "esp_err.h"
#include "esp_partition.h"
#include "esp_littlefs.h"

#define STORAGE_LABEL "storage"
#define MOUNT_PATH "/fs"
#define SEED_FILE "FIXTURE.TXT"
#define PROOF_FILE "PROOF.TXT"

static const char seed[] = "M5EMU_SEEDED_IDF_LITTLEFS_PAYLOAD";
static const char proof[] = "M5EMU_LITTLEFS_GUEST_WRITE";

static bool matches(const char *path, const char *expected)
{
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return false;
    }
    char actual[64];
    size_t bytes = fread(actual, 1, sizeof(actual), file);
    fclose(file);
    return bytes == strlen(expected) && memcmp(actual, expected, bytes) == 0;
}

static bool listed(const char *filename)
{
    DIR *root = opendir(MOUNT_PATH);
    if (root == NULL) {
        return false;
    }
    struct dirent *item;
    bool exists = false;
    while ((item = readdir(root)) != NULL) {
        if (strcmp(item->d_name, filename) == 0) {
            exists = true;
            break;
        }
    }
    closedir(root);
    return exists;
}

void app_main(void)
{
    const esp_partition_t *partition = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_LITTLEFS, STORAGE_LABEL);
    if (partition == NULL) {
        puts("LITTLEFS_PROBE_PARTITION_MISSING");
        puts("LITTLEFS_PROBE_DONE");
        return;
    }
    printf("LITTLEFS_PROBE_PARTITION offset=0x%lx size=0x%lx\n",
           (unsigned long)partition->address, (unsigned long)partition->size);
    const esp_vfs_littlefs_conf_t config = {
        .base_path = MOUNT_PATH,
        .partition_label = STORAGE_LABEL,
        .format_if_mount_failed = false,
    };
    esp_err_t err = esp_vfs_littlefs_register(&config);
    if (err != ESP_OK) {
        printf("LITTLEFS_PROBE_MOUNT_ERROR %s\n", esp_err_to_name(err));
        puts("LITTLEFS_PROBE_DONE");
        return;
    }
    printf("LITTLEFS_PROBE_READ seeded=%d listed=%d prior=%d\n",
           matches(MOUNT_PATH "/" SEED_FILE, seed), listed(SEED_FILE),
           matches(MOUNT_PATH "/" PROOF_FILE, proof));
    FILE *file = fopen(MOUNT_PATH "/" PROOF_FILE, "wb");
    bool write_ok = false;
    if (file != NULL) {
        write_ok = fwrite(proof, 1, sizeof(proof) - 1, file) == sizeof(proof) - 1;
        write_ok = fclose(file) == 0 && write_ok;
    }
    ESP_ERROR_CHECK(esp_vfs_littlefs_unregister(STORAGE_LABEL));
    ESP_ERROR_CHECK(esp_vfs_littlefs_register(&config));
    printf("LITTLEFS_PROBE_REMOUNT wrote=%d restored=%d listed=%d\n", write_ok,
           matches(MOUNT_PATH "/" PROOF_FILE, proof), listed(PROOF_FILE));
    ESP_ERROR_CHECK(esp_vfs_littlefs_unregister(STORAGE_LABEL));
    puts("LITTLEFS_PROBE_DONE");
}
