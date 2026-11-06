/* Read-only Dolby DSP module query. Never changes routing, gain, or DAP state. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
struct apm_header { uint32_t miid, parameter, error, size; };
int main(int argc, char **argv) {
    uint32_t session = argc > 1 ? strtoul(argv[1], NULL, 0) : 31;
    uint32_t aif = argc > 2 ? strtoul(argv[2], NULL, 0) : UINT32_MAX;
    void *lib = dlopen("libagmclient.so", RTLD_NOW);
    if (!lib) { fprintf(stderr, "%s\n", dlerror()); return 1; }
    int (*tags)(uint32_t, uint32_t, void *, size_t *) = dlsym(lib, "agm_session_aif_get_tag_module_info");
    int (*get)(uint32_t, void *, size_t) = dlsym(lib, "agm_session_get_params");
    if (!tags || !get) return 2;
    size_t size = 4096;
    uint8_t data[4096] = {0};
    int status = tags(session, aif, data, &size);
    printf("SESSION=%u AIF=%u TAGS status=%d size=%zu\n", session, aif, status, size);
    if (status || size > sizeof(data) || size < 4) return 3;
    uint32_t total = *(uint32_t *)data, miid = 0;
    size_t offset = 4;
    for (uint32_t i = 0; i < total && offset + 8 <= size; ++i) {
        uint32_t *tag = (uint32_t *)(data + offset);
        if (tag[1] > (size - offset - 8) / 8) return 4;
        for (uint32_t j = 0; j < tag[1]; ++j) {
            printf("TAG=%08x MID=%08x MIID=%08x\n", tag[0], tag[2+j*2], tag[3+j*2]);
            if (tag[0] == 0xc00000db) miid = tag[3+j*2];
        }
        offset += 8 + tag[1] * 8;
    }
    if (!miid) return 5;
    uint8_t payload[24] = {0};
    struct apm_header *header = (struct apm_header *)payload;
    header->miid = miid;
    header->parameter = 0x00010904; // stock QdspDriver::doSetDapModuleEnabled
    header->size = 4;
    status = get(session, payload, sizeof(payload));
    printf("DAP_ENABLE status=%d DSP_error=%u miid=%x value=%u bytes=%u\n",
        status, header->error, miid, *(uint32_t *)(payload + 16), header->size);
    return status ? 6 : 0;
}
