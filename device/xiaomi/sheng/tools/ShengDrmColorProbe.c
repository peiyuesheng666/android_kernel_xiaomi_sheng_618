/* SPDX-License-Identifier: Apache-2.0
 * Read-only CRTC color-property/PCC-blob query. No mode or framebuffer access.
 */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <drm.h>
#include <drm_mode.h>

#define MAX_ITEMS 4096u
#define MAX_BLOB 65536u
static uint64_t pointer(const void *value) { return (uint64_t)(uintptr_t)value; }
static int query(int fd, unsigned long request, void *value) {
    int result;
    do { result = ioctl(fd, request, value); } while (result < 0 && errno == EINTR);
    if (result < 0) perror("read-only DRM query");
    return result;
}

static int pcc_blob(int fd, uint64_t id) {
    if (!id) return 0;
    if (id > UINT32_MAX) return -1;
    struct drm_mode_get_blob blob = {.blob_id = (uint32_t)id};
    if (query(fd, DRM_IOCTL_MODE_GETPROPBLOB, &blob) < 0 || !blob.length ||
            blob.length > MAX_BLOB || blob.length % sizeof(uint32_t)) return -1;
    uint32_t capacity = blob.length;
    uint32_t *words = calloc(1, capacity);
    if (!words) return -1;
    blob.data = pointer(words);
    if (query(fd, DRM_IOCTL_MODE_GETPROPBLOB, &blob) < 0 || blob.length > capacity) {
        free(words);
        return -1;
    }
    printf("PCC_BLOB id=%u bytes=%u", blob.blob_id, blob.length);
    for (uint32_t i = 0; i < blob.length / sizeof(uint32_t); ++i)
        printf("%s%08" PRIx32, i % 8 ? " " : "\n", words[i]);
    puts("\nPCC_BLOB_END");
    free(words);
    return 0;
}

static int crtc_properties(int fd, uint32_t crtc) {
    for (int retry = 0; retry < 4; ++retry) {
        struct drm_mode_obj_get_properties props = {.obj_id = crtc,
                                                   .obj_type = DRM_MODE_OBJECT_CRTC};
        if (query(fd, DRM_IOCTL_MODE_OBJ_GETPROPERTIES, &props) < 0 ||
                props.count_props > MAX_ITEMS) return -1;
        uint32_t capacity = props.count_props;
        uint32_t *ids = calloc(capacity ? capacity : 1, sizeof(*ids));
        uint64_t *values = calloc(capacity ? capacity : 1, sizeof(*values));
        if (!ids || !values) { free(ids); free(values); return -1; }
        props.props_ptr = pointer(ids);
        props.prop_values_ptr = pointer(values);
        int result = query(fd, DRM_IOCTL_MODE_OBJ_GETPROPERTIES, &props);
        if (result < 0) { free(ids); free(values); return -1; }
        if (props.count_props > capacity) { free(ids); free(values); continue; }
        printf("CRTC id=%u properties=%u\n", crtc, props.count_props);
        int failed = 0;
        for (uint32_t i = 0; i < props.count_props; ++i) {
            struct drm_mode_get_property property = {.prop_id = ids[i]};
            if (query(fd, DRM_IOCTL_MODE_GETPROPERTY, &property) < 0) { failed = 1; break; }
            property.name[sizeof(property.name) - 1] = '\0';
            if (strstr(property.name, "PCC") || strstr(property.name, "DITHER") ||
                    strstr(property.name, "GAMUT") || strstr(property.name, "HSIC") ||
                    !strcmp(property.name, "ACTIVE") || !strcmp(property.name, "MODE_ID")) {
                printf("PROPERTY crtc=%u id=%u name=%s flags=%08x value=%" PRIu64 "\n",
                       crtc, ids[i], property.name, property.flags, values[i]);
                if (strstr(property.name, "PCC") && (property.flags & DRM_MODE_PROP_BLOB) &&
                        pcc_blob(fd, values[i]) < 0) failed = 1;
            }
        }
        free(ids);
        free(values);
        return failed ? -1 : 0;
    }
    return -1;
}

int main(void) {
    int fd = open("/dev/dri/card0", O_RDONLY | O_CLOEXEC);
    if (fd < 0) { perror("open DRM read-only"); return 1; }
    int status = 1;
    for (int retry = 0; retry < 4; ++retry) {
        struct drm_mode_card_res resources = {0};
        if (query(fd, DRM_IOCTL_MODE_GETRESOURCES, &resources) < 0 ||
                resources.count_crtcs > MAX_ITEMS) break;
        uint32_t capacity = resources.count_crtcs;
        uint32_t *crtcs = calloc(capacity ? capacity : 1, sizeof(*crtcs));
        if (!crtcs) break;
        resources.crtc_id_ptr = pointer(crtcs);
        resources.count_fbs = 0;
        resources.count_connectors = 0;
        resources.count_encoders = 0;
        if (query(fd, DRM_IOCTL_MODE_GETRESOURCES, &resources) < 0) { free(crtcs); break; }
        if (resources.count_crtcs > capacity) { free(crtcs); continue; }
        status = resources.count_crtcs == 0;
        for (uint32_t i = 0; i < resources.count_crtcs; ++i)
            if (crtc_properties(fd, crtcs[i]) < 0) status = 1;
        free(crtcs);
        break;
    }
    close(fd);
    return status;
}
