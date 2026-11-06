/* Read-only AGM graph/gain probe. No DSP gain or routing writes. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

struct aif_info { char name[32]; uint32_t direction; };
struct apm_header { uint32_t miid, parameter, error, size; };

int main(int argc, char **argv) {
    uint32_t session = argc > 1 ? strtoul(argv[1], NULL, 0) : 31;
    void *library = dlopen("libagmclient.so", RTLD_NOW);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    int (*list)(struct aif_info *, size_t *) = dlsym(library, "agm_get_aif_info_list");
    int (*tags)(uint32_t, uint32_t, void *, size_t *) = dlsym(library, "agm_session_aif_get_tag_module_info");
    int (*get)(uint32_t, void *, size_t) = dlsym(library, "agm_session_get_params");
    if (!list || !tags || !get) return 2;
    size_t count = 0;
    int status = list(NULL, &count);
    printf("AIF count status=%d count=%zu\n", status, count);
    if (status || !count || count > 1024) return 3;
    struct aif_info *interfaces = calloc(count, sizeof(*interfaces));
    status = list(interfaces, &count);
    if (status) return 4;
    uint32_t aif = UINT32_MAX;
    for (size_t i = 0; i < count; ++i) {
        if (!strcmp(interfaces[i].name, "TDM-LPAIF-RX-SECONDARY")) aif = i;
    }
    free(interfaces);
    if (aif == UINT32_MAX) return 5;
    printf("SESSION=%u AIF=%u\n", session, aif);
    size_t size = 4096;
    uint8_t data[4096] = {0};
    status = tags(session, aif, data, &size);
    printf("TAGS status=%d size=%zu\n", status, size);
    if (status || size > sizeof(data)) return 6;
    uint32_t total = *(uint32_t *)data;
    size_t offset = 4;
    uint32_t volume = 0;
    for (uint32_t i = 0; i < total && offset + 8 <= size; ++i) {
        uint32_t *tag = (uint32_t *)(data + offset);
        size_t next = offset + 8 + tag[1] * 8;
        if (next > size) return 7;
        for (uint32_t j = 0; j < tag[1]; ++j) {
            printf("TAG=%08x MID=%08x MIID=%08x\n", tag[0], tag[2+j*2], tag[3+j*2]);
            if (tag[0] == 0xc000000d) volume = tag[3+j*2];
        }
        offset = next;
    }
    if (!volume) return 8;
    uint8_t payload[24] = {0};
    struct apm_header *header = (struct apm_header *)payload;
    header->miid = volume;
    header->parameter = 0x08001035;
    header->size = 4;
    status = get(session, payload, sizeof(payload));
    printf("MASTER_GAIN status=%d DSP_error=%u miid=%x gain_q13=%u reserved=%u\n", status,
           header->error, volume, *(uint16_t *)(payload + 16), *(uint16_t *)(payload + 18));
    fflush(stdout);
    return status ? 9 : 0;
}
