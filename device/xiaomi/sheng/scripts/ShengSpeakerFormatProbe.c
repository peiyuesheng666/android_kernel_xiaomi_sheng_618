/* SPDX-License-Identifier: Apache-2.0
 * Temporary speaker-MFC channel-order test. Does not change saved settings.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
struct header { uint32_t miid, parameter, bytes, error; };
struct format { uint32_t rate; uint16_t width, channels, map[4]; };
struct request { struct header header; struct format format; };
int main(int argc, char **argv) {
    if (argc != 4) return 1;
    unsigned session = strtoul(argv[1], NULL, 0), aif = strtoul(argv[2], NULL, 0);
    int degrees = atoi(argv[3]);
    if (degrees < 0 || degrees > 270 || degrees % 90) return 1;
    void *library = dlopen("libagmclient.so", RTLD_NOW);
    if (!library) return 2;
    int (*tags)(uint32_t, uint32_t, void *, size_t *) = dlsym(library, "agm_session_aif_get_tag_module_info");
    int (*get)(uint32_t, void *, size_t) = dlsym(library, "agm_session_get_params");
    int (*set)(uint32_t, void *, size_t) = dlsym(library, "agm_session_set_params");
    if (!tags || !get || !set) return 3;
    uint32_t buffer[1024] = {0}, miid = 0;
    size_t bytes = sizeof(buffer), offset = 4;
    if (tags(session, aif, buffer, &bytes) || bytes > sizeof(buffer)) return 4;
    for (unsigned i = 0; i < buffer[0] && offset + 8 <= bytes; ++i) {
        uint32_t *tag = (void *)((uint8_t *)buffer + offset);
        if (tag[1] > (bytes - offset - 8) / 8) return 5;
        for (unsigned j = 0; j < tag[1]; ++j)
            if (tag[0] == 0xc0000039 && tag[2+j*2] == 0x07001015) miid = tag[3+j*2];
        offset += 8 + tag[1] * 8;
    }
    if (!miid) return 6;
    struct request request = {{miid, 0x08001024, sizeof(struct format), 0}, {0}};
    if (get(session, &request, sizeof(request)) || request.header.error || request.format.channels != 4) return 7;
    static const uint16_t maps[4][4] = {{1,8,2,9}, {8,9,1,2}, {9,2,8,1}, {2,1,9,8}};
    for (unsigned i = 0; i < 4; ++i) request.format.map[i] = maps[degrees / 90][i];
    request.header.bytes = sizeof(struct format);
    request.header.error = 0;
    int status = set(session, &request, sizeof(request));
    printf("MFC=%x ROTATION=%d SET=%d MAP=%u,%u,%u,%u\n", miid, degrees, status,
            request.format.map[0], request.format.map[1], request.format.map[2], request.format.map[3]);
    dlclose(library);
    return status ? 8 : 0;
}
