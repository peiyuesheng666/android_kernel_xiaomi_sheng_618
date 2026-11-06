/* SPDX-License-Identifier: Apache-2.0
 * Read-only queries of the active speaker graph. No audio/routing writes.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

/* SPF apm_module_param_data_t: size precedes error_code. */
struct apm_header { uint32_t miid, parameter, size, error; };
int main(int argc, char **argv) {
    if (argc < 3) return 1;
    const uint32_t session = strtoul(argv[1], NULL, 0);
    const uint32_t aif = strtoul(argv[2], NULL, 0);
    const uint32_t wanted_tag = argc > 5 ? strtoul(argv[5], NULL, 0) : 0xc00000db;
    void *lib = dlopen("libagmclient.so", RTLD_NOW);
    if (!lib) { fprintf(stderr, "%s\n", dlerror()); return 2; }
    int (*tags)(uint32_t, uint32_t, void *, size_t *) = dlsym(lib, "agm_session_aif_get_tag_module_info");
    int (*get)(uint32_t, void *, size_t) = dlsym(lib, "agm_session_get_params");
    if (!tags || !get) return 3;
    size_t size = 4096;
    uint32_t data[1024] = {0};
    int status = tags(session, aif, data, &size);
    printf("SESSION=%u AIF=%u TAGS status=%d size=%zu\n", session, aif, status, size);
    if (status || size > sizeof(data) || size < 4) return 4;
    uint32_t miid = 0;
    size_t offset = 4;
    for (uint32_t i = 0; i < data[0] && offset + 8 <= size; ++i) {
        uint32_t *tag = (uint32_t *)((uint8_t *)data + offset);
        if (tag[1] > (size - offset - 8) / 8) return 5;
        for (uint32_t j = 0; j < tag[1]; ++j) {
            printf("TAG=%08x MID=%08x MIID=%08x\n", tag[0], tag[2+j*2], tag[3+j*2]);
            if (tag[0] == wanted_tag) miid = tag[3+j*2];
        }
        offset += 8 + tag[1] * 8;
    }
    if (!miid) return 6;
    const uint32_t defaults[] = {0x08001026, 0x10904, 0x10748, 0x10743, 0x10738};
    const size_t count = argc > 3 ? 1 : sizeof(defaults)/sizeof(defaults[0]);
    for (size_t i = 0; i < count; ++i) {
        const uint32_t id = argc > 3 ? strtoul(argv[3], NULL, 0) : defaults[i];
        const uint32_t bytes = argc > 4 ? strtoul(argv[4], NULL, 0) : 4;
        if (!bytes || bytes > 4096 || bytes % 4) return 7;
        const size_t total = (sizeof(struct apm_header) + bytes + 7) & ~(size_t)7;
        uint32_t *payload = calloc(1, total);
        if (!payload) return 8;
        struct apm_header *header = (struct apm_header *)payload;
        header->miid = miid; header->parameter = id; header->size = bytes;
        status = get(session, payload, total);
        printf("DSP_QUERY param=%x status=%d error=%u miid=%x bytes=%u values=",
                id, status, header->error, header->miid, header->size);
        if (!status && !header->error && header->size <= bytes)
            for (size_t k = 0; k < header->size / 4; ++k)
                printf("%s%d", k ? "," : "", (int32_t)payload[4+k]);
        puts("");
        free(payload);
    }
    dlclose(lib);
    return 0;
}
