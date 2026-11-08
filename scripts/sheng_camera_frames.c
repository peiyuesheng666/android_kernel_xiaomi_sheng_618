// SPDX-License-Identifier: Apache-2.0
// Exercise the real stock camera HAL and discard every frame in memory.
#include <camera/NdkCameraManager.h>
#include <camera/NdkCameraMetadataTags.h>
#include <media/NdkImageReader.h>
#include <android/hardware_buffer.h>
#include <string.h>
#include <stdio.h>
#include <stdatomic.h>
#include <time.h>
#include <unistd.h>

static atomic_int frames, errors, completed, failed;
static void capture_completed(void *ctx, ACameraCaptureSession *session, ACaptureRequest *request, const ACameraMetadata *result) {
    atomic_fetch_add(&completed, 1);
}
static void capture_failed(void *ctx, ACameraCaptureSession *session, ACaptureRequest *request, ACameraCaptureFailure *failure) {
    if (atomic_fetch_add(&failed, 1) < 3) printf("capture_failed reason=%d frame=%lld\n", failure->reason, (long long)failure->frameNumber);
}
static void disconnected(void *ctx, ACameraDevice *dev) { atomic_fetch_add(&errors, 1); }
static void device_error(void *ctx, ACameraDevice *dev, int error) {
    atomic_fetch_add(&errors, 1); printf("device_error=%d\n", error);
}
static void session_state(void *ctx, ACameraCaptureSession *session) { }
static void image_available(void *ctx, AImageReader *reader) {
    AImage *image = NULL;
    if (AImageReader_acquireLatestImage(reader, &image) == AMEDIA_OK && image) {
        atomic_fetch_add(&frames, 1);
        AImage_delete(image); // Never inspect, export or save pixel data.
    }
}

static int exercise(ACameraManager *manager, const char *id, int format) {
    ACameraMetadata *metadata = NULL;
    ACameraDevice *device = NULL;
    AImageReader *reader = NULL;
    ACaptureRequest *request = NULL;
    ACaptureSessionOutputContainer *container = NULL;
    ACaptureSessionOutput *output = NULL;
    ACameraOutputTarget *target = NULL;
    ACameraCaptureSession *session = NULL;
    ANativeWindow *window = NULL;
    int result = 1, width = 0, height = 0;
    ACameraMetadata_const_entry configs;
    atomic_store(&frames, 0); atomic_store(&errors, 0);
    atomic_store(&completed, 0); atomic_store(&failed, 0);
    int meta_status = ACameraManager_getCameraCharacteristics(manager, id, &metadata);
    printf("camera=%s metadata_status=%d format=%d\n", id, meta_status, format);
    if (meta_status != ACAMERA_OK) goto done;
    if (ACameraMetadata_getConstEntry(metadata, ACAMERA_SCALER_AVAILABLE_STREAM_CONFIGURATIONS, &configs) != ACAMERA_OK) goto done;
    for (unsigned int i = 0; i + 3 < configs.count; i += 4) {
        const int32_t *c = configs.data.i32 + i;
        if (c[0] == format && c[3] == 0 && c[1] >= 640 && c[1] <= 4096 &&
            (!width || c[1] * c[2] < width * height)) { width = c[1]; height = c[2]; }
    }
    if (!width) goto done;
    uint64_t usage = format == AIMAGE_FORMAT_PRIVATE ? AHARDWAREBUFFER_USAGE_GPU_SAMPLED_IMAGE : AHARDWAREBUFFER_USAGE_CPU_READ_OFTEN;
    if (AImageReader_newWithUsage(width, height, format, usage, 8, &reader) != AMEDIA_OK) goto done;
    AImageReader_ImageListener listener = { .context = NULL, .onImageAvailable = image_available };
    if (AImageReader_setImageListener(reader, &listener) != AMEDIA_OK) goto done;
    if (AImageReader_getWindow(reader, &window) != AMEDIA_OK) goto done;
    ACameraDevice_StateCallbacks devcb = { .context = NULL, .onDisconnected = disconnected, .onError = device_error };
    int status = ACameraManager_openCamera(manager, id, &devcb, &device);
    printf("camera=%s open_status=%d size=%dx%d\n", id, status, width, height); fflush(stdout);
    if (status != ACAMERA_OK) goto done;
    if (ACaptureSessionOutputContainer_create(&container) != ACAMERA_OK) goto done;
    if (ACaptureSessionOutput_create(window, &output) != ACAMERA_OK) goto done;
    if (ACaptureSessionOutputContainer_add(container, output) != ACAMERA_OK) goto done;
    if (ACameraDevice_createCaptureRequest(device, TEMPLATE_PREVIEW, &request) != ACAMERA_OK) goto done;
    if (ACameraOutputTarget_create(window, &target) != ACAMERA_OK) goto done;
    if (ACaptureRequest_addTarget(request, target) != ACAMERA_OK) goto done;
    ACameraCaptureSession_stateCallbacks sesscb = { .context = NULL, .onClosed = session_state, .onReady = session_state, .onActive = session_state };
    status = ACameraDevice_createCaptureSession(device, container, &sesscb, &session);
    printf("camera=%s session_status=%d\n", id, status); fflush(stdout);
    if (status != ACAMERA_OK) goto done;
    ACameraCaptureSession_captureCallbacks capturecb = { .context = NULL, .onCaptureCompleted = capture_completed, .onCaptureFailed = capture_failed };
    status = ACameraCaptureSession_setRepeatingRequest(session, &capturecb, 1, &request, NULL);
    printf("camera=%s repeating_status=%d\n", id, status); fflush(stdout);
    if (status != ACAMERA_OK) goto done;
    for (int i = 0; i < 60 && !atomic_load(&errors); i++) usleep(100000);
    result = atomic_load(&frames) >= 5 && !atomic_load(&errors) ? 0 : 1;
done:
    if (session) { ACameraCaptureSession_stopRepeating(session); ACameraCaptureSession_close(session); }
    if (device) ACameraDevice_close(device);
    if (request) ACaptureRequest_free(request);
    if (target) ACameraOutputTarget_free(target);
    if (container && output) ACaptureSessionOutputContainer_remove(container, output);
    if (output) ACaptureSessionOutput_free(output);
    if (container) ACaptureSessionOutputContainer_free(container);
    if (reader) AImageReader_delete(reader);
    if (metadata) ACameraMetadata_free(metadata);
    printf("RESULT camera=%s frames=%d completed=%d failed=%d errors=%d passed=%d\n", id, atomic_load(&frames), atomic_load(&completed), atomic_load(&failed), atomic_load(&errors), !result);
    fflush(stdout);
    return result;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    ACameraManager *manager = ACameraManager_create();
    ACameraIdList *ids = NULL;
    if (!manager || ACameraManager_getCameraIdList(manager, &ids) != ACAMERA_OK) return 2;
    printf("accessible_cameras=%d\n", ids->numCameras);
    int failed = 0, tested = 0;
    int format = argc > 2 && !strcmp(argv[2], "private") ? AIMAGE_FORMAT_PRIVATE : AIMAGE_FORMAT_YUV_420_888;
    for (int i = 0; i < ids->numCameras && i < 4; i++) {
        if (argc > 1 && strcmp(argv[1], ids->cameraIds[i])) continue;
        tested++;
        failed += exercise(manager, ids->cameraIds[i], format);
    }
    ACameraManager_deleteCameraIdList(ids);
    ACameraManager_delete(manager);
    return !tested ? 3 : failed ? 1 : 0;
}
