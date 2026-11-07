/* SPDX-License-Identifier: Apache-2.0
 * Read-only sheng DRM mode-property query. No pixels or mode changes.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <drm.h>
#include <drm_mode.h>

#define MAX_ITEMS 4096u
#define MAX_BLOB (1024u * 1024u)
#define MAX_RETRIES 5

static uint64_t pointer(const void *p) { return (uint64_t)(uintptr_t)p; }

static int query(int fd, unsigned long request, void *arg) {
    int result;
    do { result = ioctl(fd, request, arg); } while (result < 0 && errno == EINTR);
    if (result < 0) perror("read-only DRM query");
    return result;
}

static void *array(uint32_t count, size_t item_size) {
    if (count > MAX_ITEMS) {
        fprintf(stderr, "DRM item count exceeds bound: %u\n", count);
        return NULL;
    }
    return calloc(count ? count : 1, item_size);
}

static int dump_blob(int fd, uint64_t id) {
    if (!id || id > UINT32_MAX) {
        fprintf(stderr, "Invalid mode-property blob id: %llu\n", (unsigned long long)id);
        return -1;
    }
    struct drm_mode_get_blob blob = { .blob_id = (uint32_t)id };
    if (query(fd, DRM_IOCTL_MODE_GETPROPBLOB, &blob) < 0) return -1;
    if (!blob.length || blob.length > MAX_BLOB) {
        fprintf(stderr, "Invalid mode-property blob length: %u\n", blob.length);
        return -1;
    }
    const uint32_t capacity = blob.length;
    unsigned char *data = calloc((size_t)capacity + 1, 1);
    if (!data) return -1;
    blob.data = pointer(data);
    if (query(fd, DRM_IOCTL_MODE_GETPROPBLOB, &blob) < 0 || blob.length > capacity) {
        free(data);
        return -1;
    }
    printf("MODE_PROPERTIES_BEGIN blob=%u bytes=%u\n", blob.blob_id, blob.length);
    if (fwrite(data, 1, blob.length, stdout) != blob.length) {
        free(data);
        return -1;
    }
    printf("\nMODE_PROPERTIES_END\n");
    free(data);
    return 0;
}

static int dump_connector(int fd, uint32_t id) {
    struct drm_mode_modeinfo dummy = {0};
    struct drm_mode_get_connector connector = {
        .connector_id = id, .count_modes = 1, .modes_ptr = pointer(&dummy),
    };
    /* count_modes=1 avoids the GETCONNECTOR forced-probe path. */
    if (query(fd, DRM_IOCTL_MODE_GETCONNECTOR, &connector) < 0) return -1;
    if (connector.connector_type != DRM_MODE_CONNECTOR_DSI || connector.connection != 1)
        return 0;
    for (int retry = 0; retry < MAX_RETRIES; ++retry) {
        uint32_t modes_count = connector.count_modes;
        uint32_t props_count = connector.count_props;
        uint32_t encoders_count = connector.count_encoders;
        struct drm_mode_modeinfo *modes = array(modes_count, sizeof(*modes));
        uint32_t *props = array(props_count, sizeof(*props));
        uint64_t *values = array(props_count, sizeof(*values));
        uint32_t *encoders = array(encoders_count, sizeof(*encoders));
        if (!modes || !props || !values || !encoders) {
            free(modes); free(props); free(values); free(encoders);
            return -1;
        }
        connector.modes_ptr = pointer(modes);
        connector.props_ptr = pointer(props);
        connector.prop_values_ptr = pointer(values);
        connector.encoders_ptr = pointer(encoders);
        connector.count_modes = modes_count ? modes_count : 1;
        connector.count_props = props_count;
        connector.count_encoders = encoders_count;
        int result = query(fd, DRM_IOCTL_MODE_GETCONNECTOR, &connector);
        if (result < 0) {
            free(modes); free(props); free(values); free(encoders);
            return -1;
        }
        if (connector.count_modes != modes_count || connector.count_props != props_count ||
            connector.count_encoders != encoders_count) {
            free(modes); free(props); free(values); free(encoders);
            continue;
        }
        printf("DSI connector=%u connected=%u modes=%u properties=%u\n", id,
               connector.connection, modes_count, props_count);
        for (uint32_t i = 0; i < modes_count; ++i)
            printf("MODE name=%.*s size=%ux%u refresh=%u timing_clock_khz=%u type=0x%x\n",
                   (int)sizeof(modes[i].name), modes[i].name, modes[i].hdisplay,
                   modes[i].vdisplay, modes[i].vrefresh, modes[i].clock, modes[i].type);
        int found = 0;
        for (uint32_t i = 0; i < props_count; ++i) {
            struct drm_mode_get_property property = { .prop_id = props[i] };
            if (query(fd, DRM_IOCTL_MODE_GETPROPERTY, &property) < 0) {
                result = -1;
                break;
            }
            property.name[sizeof(property.name) - 1] = '\0';
            if (!strcmp(property.name, "mode_properties") ||
                !strcmp(property.name, "MODE_PROPERTIES")) {
                found = 1;
                if (!(property.flags & DRM_MODE_PROP_BLOB) || dump_blob(fd, values[i]) < 0)
                    result = -1;
            }
        }
        free(modes); free(props); free(values); free(encoders);
        if (!found) {
            fprintf(stderr, "DSI mode_properties blob unavailable\n");
            return -1;
        }
        return result < 0 ? -1 : 1;
    }
    fprintf(stderr, "Connector counts did not stabilize\n");
    return -1;
}

int main(void) {
    int fd = open("/dev/dri/card0", O_RDONLY | O_CLOEXEC);
    if (fd < 0) { perror("open /dev/dri/card0 read-only"); return 1; }
    struct drm_mode_card_res resources = {0};
    if (query(fd, DRM_IOCTL_MODE_GETRESOURCES, &resources) < 0) { close(fd); return 1; }
    int status = 1;
    for (int retry = 0; retry < MAX_RETRIES; ++retry) {
        uint32_t count = resources.count_connectors;
        uint32_t *connectors = array(count, sizeof(*connectors));
        if (!connectors) break;
        resources.connector_id_ptr = pointer(connectors);
        resources.count_connectors = count;
        resources.count_fbs = 0;
        resources.count_crtcs = 0;
        resources.count_encoders = 0;
        if (query(fd, DRM_IOCTL_MODE_GETRESOURCES, &resources) < 0) { free(connectors); break; }
        if (resources.count_connectors > count) { free(connectors); continue; }
        int found = 0, failed = 0;
        for (uint32_t i = 0; i < resources.count_connectors; ++i) {
            int result = dump_connector(fd, connectors[i]);
            if (result < 0) failed = 1;
            else if (result > 0) found = 1;
        }
        free(connectors);
        status = !found || failed;
        break;
    }
    close(fd);
    return status;
}
