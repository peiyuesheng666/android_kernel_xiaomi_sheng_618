/* SPDX-License-Identifier: Apache-2.0
 * Bounded, temporary channel-mixer test on the final four-channel speaker MFC.
 * No saved Dolby settings, gains, amplifier controls or partition writes.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

struct header { uint32_t miid, parameter, bytes, error; };
struct format { uint32_t rate; uint16_t width, channels, map[4]; };
struct request { struct header header; struct format format; };

static size_t table(uint8_t *destination, const uint16_t *output,
                    const uint16_t *input, unsigned count, unsigned pose) {
    static const unsigned order[4][4] = {
        {3,1,2,0}, {1,0,3,2}, {0,2,1,3}, {2,3,0,1}
    };
    uint16_t *p = (void *)destination;
    *p++ = 4;
    *p++ = count;
    memcpy(p, output, 8); p += 4;
    memcpy(p, input, count * 2); p += count;
    for (unsigned row = 0; row < 4; ++row)
        for (unsigned col = 0; col < count; ++col)
            *p++ = col == (count == 4 ? order[pose][row] : order[pose][row] % 2)
                    ? 0x4000 : 0;
    size_t bytes = (uint8_t *)p - destination;
    return (bytes + 3) & ~(size_t)3;
}

int main(int argc, char **argv) {
    if (argc != 5) return 1;
    unsigned session = strtoul(argv[1], NULL, 0), aif = strtoul(argv[2], NULL, 0);
    uint32_t wanted = strtoul(argv[3], NULL, 0);
    int degrees = atoi(argv[4]);
    if (degrees < 0 || degrees > 270 || degrees % 90) return 1;
    void *library = dlopen("libagmclient.so", RTLD_NOW);
    if (!library) return 2;
    int (*tags)(uint32_t, uint32_t, void *, size_t *) = dlsym(library, "agm_session_aif_get_tag_module_info");
    int (*get)(uint32_t, void *, size_t) = dlsym(library, "agm_session_get_params");
    int (*set)(uint32_t, void *, size_t) = dlsym(library, "agm_session_set_params");
    if (!tags || !get || !set) return 3;
    uint32_t buffer[1024] = {0}, miid = 0, predecessor = 0;
    size_t bytes = sizeof(buffer), offset = 4;
    if (tags(session, aif, buffer, &bytes) || bytes > sizeof(buffer) || bytes < 4) return 4;
    for (unsigned i = 0; i < buffer[0] && offset + 8 <= bytes; ++i) {
        uint32_t *tag = (void *)((uint8_t *)buffer + offset);
        if (tag[1] > (bytes - offset - 8) / 8) return 5;
        for (unsigned j = 0; j < tag[1]; ++j) {
            if (tag[0] == wanted && tag[2+j*2] == 0x07001015) miid = tag[3+j*2];
            if (tag[0] == 0xc0000039 && tag[2+j*2] == 0x07001015) predecessor = tag[3+j*2];
        }
        offset += 8 + tag[1] * 8;
    }
    if (!miid) return 6;
    struct request format = {{miid, 0x08001024, sizeof(struct format), 0}, {0}};
    if (get(session, &format, sizeof(format)) || format.header.error || format.format.channels != 4) return 7;
    printf("MFC=%x OUTPUT=%u,%u,%u,%u\n", miid, format.format.map[0],
            format.format.map[1], format.format.map[2], format.format.map[3]);
    uint8_t payload[512] = {0};
    struct header *header = (void *)payload;
    uint32_t *tables = (void *)(payload + sizeof(*header));
    *tables = 3;
    static const uint16_t quad[] = {1,2,8,9}, factory[] = {1,2,4,5}, stereo[] = {1,2};
    offset = sizeof(*header) + sizeof(*tables);
    offset += table(payload + offset, format.format.map, quad, 4, degrees / 90);
    offset += table(payload + offset, format.format.map, factory, 4, degrees / 90);
    offset += table(payload + offset, format.format.map, stereo, 2, degrees / 90);
    if (wanted == 0xc000003d && predecessor) {
        struct request input = {{predecessor, 0x08001024, sizeof(struct format), 0}, {0}};
        if (!get(session, &input, sizeof(input)) && !input.header.error && input.format.channels == 4 &&
                memcmp(input.format.map, quad, 8) && memcmp(input.format.map, factory, 8)) {
            offset += table(payload + offset, format.format.map, input.format.map, 4, degrees / 90);
            ++*tables;
            printf("ACTUAL_INPUT=%u,%u,%u,%u\n", input.format.map[0], input.format.map[1],
                    input.format.map[2], input.format.map[3]);
        }
    }
    header->miid = miid;
    header->parameter = 0x0800101f;
    header->bytes = offset - sizeof(*header);
    int status = set(session, payload, (offset + 7) & ~(size_t)7);
    printf("MATRIX_ROTATION=%d TABLES=%u SET=%d BYTES=%u\n", degrees, *tables, status, header->bytes);
    dlclose(library);
    return status ? 8 : 0;
}
