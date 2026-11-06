/* SPDX-License-Identifier: Apache-2.0
 * Inspect stock calibration topology in this process only. No DSP/audio writes.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include "acdb.h"

struct apm_header { uint32_t miid, parameter, size, error; };
static void inspect(const AcdbBlob *blob) {
    size_t offset = 0;
    while (offset + sizeof(struct apm_header) <= blob->buf_size) {
        const struct apm_header *header = (const void *)((const uint8_t *)blob->buf + offset);
        if (header->size > blob->buf_size - offset - sizeof(*header)) break;
        const uint32_t *data = (const void *)(header + 1);
        printf("APM miid=%x param=%x bytes=%u\n", header->miid, header->parameter, header->size);
        if (header->miid == 0x401d || header->miid == 0x4174 || header->miid == 0x4615) {
            printf("STOCK_MODULE miid=%x param=%x words=", header->miid, header->parameter);
            for (uint32_t i = 0; i < header->size / 4 && i < 64; ++i)
                printf("%s%08x", i ? "," : "", data[i]);
            puts("");
        }
        if (header->parameter == 0x08001004 && header->size >= 4) {
            uint32_t count = data[0];
            if (count <= (header->size - 4) / 16) {
                for (uint32_t i = 0; i < count; ++i) {
                    const uint32_t *edge = data + 1 + i * 4;
                    printf("EDGE %x:%x -> %x:%x\n", edge[0], edge[1], edge[2], edge[3]);
                }
            }
        }
        offset += (sizeof(*header) + header->size + 7) & ~(size_t)7;
    }
}

int main(int argc, char **argv) {
    if ((argc - 1) % 2 || argc > 33) return 1;
    void *library = dlopen("libar-acdb.so", RTLD_NOW);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); return 2; }
    int (*init)(AcdbDataFiles *, AcdbFile *) = dlsym(library, "acdb_init");
    int (*ioctl_fn)(uint32_t, void *, uint32_t, void *, uint32_t) = dlsym(library, "acdb_ioctl");
    int (*deinit)(void) = dlsym(library, "acdb_deinit");
    if (!init || !ioctl_fn || !deinit) return 3;
    AcdbDataFiles files = {0};
    const char *paths[] = {
        "/vendor/etc/acdbdata/kalama_mtp/Forte_acdb_cal.acdb",
        "/vendor/etc/acdbdata/kalama_mtp/Forte_workspaceFileXml.qwsp"
    };
    files.num_files = 2;
    for (size_t i = 0; i < 2; ++i) {
        files.acdbFiles[i].fileNameLen = strlen(paths[i]);
        memcpy(files.acdbFiles[i].fileName, paths[i], strlen(paths[i]) + 1);
    }
    int result = init(&files, NULL);
    printf("ACDB_INIT result=%d\n", result);
    if (result) return 4;
    AcdbKeyValuePair keys[16] = {{0xa1000000,0xa1000001}, {0xa2000000,0xa2000001},
                               {0xab000000,1}, {0xac000000,0xac000002}};
    uint32_t count = argc > 1 ? (argc - 1) / 2 : 4;
    if (argc > 1) for (uint32_t i = 0; i < count; ++i) {
        keys[i].key = strtoul(argv[1 + i * 2], NULL, 0);
        keys[i].value = strtoul(argv[2 + i * 2], NULL, 0);
    }
    AcdbGraphKeyVector gkv = {count, keys};
    AcdbGetGraphRsp graph = {0};
    result = ioctl_fn(ACDB_CMD_GET_GRAPH, &gkv, sizeof(gkv), &graph, sizeof(graph));
    printf("ACDB_GRAPH size-query=%d count=%u bytes=%u\n", result, graph.num_subgraphs, graph.size);
    if (result || !graph.size || graph.size > 1024*1024) return 5;
    graph.subgraphs = calloc(1, graph.size);
    if (!graph.subgraphs) return 6;
    result = ioctl_fn(ACDB_CMD_GET_GRAPH, &gkv, sizeof(gkv), &graph, sizeof(graph));
    if (result || graph.num_subgraphs > 1024) return 7;
    uint32_t ids[1024] = {0};
    size_t offset = 0;
    for (uint32_t i = 0; i < graph.num_subgraphs; ++i) {
        if (offset + 8 > graph.size) return 8;
        const AcdbSubgraph *sg = (const void *)((const uint8_t *)graph.subgraphs + offset);
        if (sg->num_dst_sgids > (graph.size-offset-8)/4) return 9;
        ids[i] = sg->sg_id;
        printf("SUBGRAPH %x\n", ids[i]);
        offset += 8 + sg->num_dst_sgids * 4;
    }
    AcdbSgIdGraphKeyVector request = {graph.num_subgraphs, ids, gkv};
    AcdbGetSubgraphDataRsp response = {0};
    result = ioctl_fn(ACDB_CMD_GET_SUBGRAPH_DATA, &request, sizeof(request), &response, sizeof(response));
    printf("ACDB_DATA size-query=%d spf=%u properties=%u\n", result, response.spf_blob.buf_size, response.driver_prop.size);
    if (result || response.spf_blob.buf_size > 1024*1024 || response.driver_prop.size > 1024*1024) return 10;
    response.spf_blob.buf = calloc(1, response.spf_blob.buf_size);
    response.driver_prop.sub_graph_prop_data = calloc(1, response.driver_prop.size);
    if (!response.spf_blob.buf || !response.driver_prop.sub_graph_prop_data) return 11;
    result = ioctl_fn(ACDB_CMD_GET_SUBGRAPH_DATA, &request, sizeof(request), &response, sizeof(response));
    printf("ACDB_DATA result=%d\n", result);
    if (!result) inspect(&response.spf_blob);
    AcdbSubGraphList links = {graph.num_subgraphs, graph.subgraphs};
    AcdbBlob connections = {0};
    result = ioctl_fn(ACDB_CMD_GET_SUBGRAPH_CONNECTIONS, &links, sizeof(links), &connections, sizeof(connections));
    if (!result && connections.buf_size && connections.buf_size <= 1024*1024) {
        connections.buf = calloc(1, connections.buf_size);
        if (connections.buf) {
            result = ioctl_fn(ACDB_CMD_GET_SUBGRAPH_CONNECTIONS, &links, sizeof(links), &connections, sizeof(connections));
            printf("ACDB_CONNECTIONS result=%d\n", result);
            if (!result) inspect(&connections);
        }
    }
    free(connections.buf);
    free(response.spf_blob.buf);
    free(response.driver_prop.sub_graph_prop_data);
    free(graph.subgraphs);
    deinit();
    dlclose(library);
    return result ? 12 : 0;
}
