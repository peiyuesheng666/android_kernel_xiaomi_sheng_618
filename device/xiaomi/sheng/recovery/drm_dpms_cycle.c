// SPDX-License-Identifier: Apache-2.0
// Explicit temporary display power cycle via the running recovery's DRM file.
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <drm.h>
#include <drm_mode.h>

int main(int argc,char **argv) {
    if (argc!=3) {fprintf(stderr,"usage: drm-dpms-cycle RECOVERY_PID DRM_FD\n");return 2;}
    int pid=atoi(argv[1]),number=atoi(argv[2]);
    if (pid<2 || number<0) return 2;
    char path[128],target[256];
    snprintf(path,sizeof(path),"/proc/%d/exe",pid);
    ssize_t len=readlink(path,target,sizeof(target)-1);
    if (len<0) {perror("read recovery executable");return 1;}
    target[len]=0;
    if (strcmp(target,"/system/bin/recovery")) {fprintf(stderr,"Refusing other process: %s\n",target);return 2;}
    snprintf(path,sizeof(path),"/proc/%d/fd/%d",pid,number);
    len=readlink(path,target,sizeof(target)-1);
    if (len<0) {perror("read DRM descriptor");return 1;}
    target[len]=0;
    if (strcmp(target,"/dev/dri/card0")) {fprintf(stderr,"Refusing other descriptor: %s\n",target);return 2;}
    int pidfd=(int)syscall(SYS_pidfd_open,pid,0);
    if (pidfd<0) {perror("pidfd_open");return 1;}
    int fd=(int)syscall(SYS_pidfd_getfd,pidfd,number,0);
    close(pidfd);
    if (fd<0) {perror("pidfd_getfd: no display state changed");return 1;}
    uint32_t connectors[64]={0};
    struct drm_mode_card_res resources={.connector_id_ptr=(uintptr_t)connectors,.count_connectors=64};
    if (ioctl(fd,DRM_IOCTL_MODE_GETRESOURCES,&resources)) {perror("resources");close(fd);return 1;}
    for (uint32_t i=0;i<resources.count_connectors && i<64;++i) {
        struct drm_mode_modeinfo modes[128];
        uint32_t properties[128],encoders[128];
        uint64_t values[128];
        struct drm_mode_get_connector connector={.connector_id=connectors[i],
            .modes_ptr=(uintptr_t)modes,.count_modes=128,
            .props_ptr=(uintptr_t)properties,.prop_values_ptr=(uintptr_t)values,.count_props=128,
            .encoders_ptr=(uintptr_t)encoders,.count_encoders=128};
        if (ioctl(fd,DRM_IOCTL_MODE_GETCONNECTOR,&connector) || connector.connector_type!=DRM_MODE_CONNECTOR_DSI) continue;
        for (uint32_t j=0;j<connector.count_props && j<128;++j) {
            struct drm_mode_get_property property={.prop_id=properties[j]};
            if (ioctl(fd,DRM_IOCTL_MODE_GETPROPERTY,&property) || strcmp(property.name,"DPMS")) continue;
            printf("DSI connector=%u DPMS property=%u original=%" PRIu64 "\n",connector.connector_id,property.prop_id,(uint64_t)values[j]);
            if (values[j]!=DRM_MODE_DPMS_ON) {puts("Display was not ON; no cycle performed");close(fd);return 2;}
            struct drm_mode_connector_set_property change={.connector_id=connector.connector_id,
                .prop_id=property.prop_id,.value=DRM_MODE_DPMS_OFF};
            if (ioctl(fd,DRM_IOCTL_MODE_SETPROPERTY,&change)) {perror("DPMS off");close(fd);return 1;}
            usleep(500000);
            change.value=values[j];
            int result=ioctl(fd,DRM_IOCTL_MODE_SETPROPERTY,&change);
            if (result) {perror("DPMS restore");result=ioctl(fd,DRM_IOCTL_MODE_SETPROPERTY,&change);}
            puts(result?"FAILED to restore original display state":"Display OFF/ON cycle completed; original ON value restored");
            close(fd);
            return result?1:0;
        }
    }
    puts("No DSI DPMS property found; no display state changed");
    close(fd);
    return 2;
}
