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
    if (argc != 4 && argc != 5) return 1;
    unsigned session = strtoul(argv[1], NULL, 0), aif = strtoul(argv[2], NULL, 0);
    uint32_t wanted = argc == 5 ? strtoul(argv[4], NULL, 0) : 0xc0000039;
    if (wanted != 0xc0000039 && wanted != 0xc000003d) return 1;
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
            if (tag[0] == wanted && tag[2+j*2] == 0x07001015) miid = tag[3+j*2];
        offset += 8 + tag[1] * 8;
    }
    if (!miid) return 6;
    struct request request = {{miid, 0x08001024, sizeof(struct format), 0}, {0}};
    if (get(session, &request, sizeof(request)) || request.header.error || request.format.channels != 4) return 7;
    static const uint16_t maps[4][4] = {{1,8,2,9}, {8,9,1,2}, {9,2,8,1}, {2,1,9,8}};
    for (unsigned i = 0; i < 4; ++i) {
        uint16_t channel = maps[degrees / 90][i];
        // The final stock MFC's layout is FL/FR/LS/RS (1/2/4/5),
        // distinct from the earlier test's FL/FR/LB/RB numbering.
        if (wanted == 0xc000003d && channel >= 8) channel -= 4;
        request.format.map[i] = channel;
    }
    if (wanted == 0xc000003d) {
        struct { struct header header; uint32_t count, padding; } reset =
                {{miid, 0x0800101f, 4, 0}, 0, 0};
        int reset_status = set(session, &reset, sizeof(reset));
        if (reset_status) return 8;
    }
    request.header.bytes = sizeof(struct format);
    request.header.error = 0;
    int status = set(session, &request, sizeof(request));
    printf("MFC=%x ROTATION=%d SET=%d MAP=%u,%u,%u,%u\n", miid, degrees, status,
            request.format.map[0], request.format.map[1], request.format.map[2], request.format.map[3]);
    dlclose(library);
    return status ? 8 : 0;
}
