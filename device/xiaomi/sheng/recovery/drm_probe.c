// SPDX-License-Identifier: Apache-2.0
// Diagnostic queries only: no SETCRTC, ATOMIC, PAGE_FLIP or display-master grab.
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <drm.h>
#include <drm_mode.h>
#include <drm_fourcc.h>

static uint32_t framebuffers[128];
static unsigned int framebuffer_count;

static void add_fb(uint32_t id) {
    if (!id) return;
    for (unsigned int i=0;i<framebuffer_count;++i) if (framebuffers[i]==id) return;
    if (framebuffer_count<128) framebuffers[framebuffer_count++]=id;
}

static void pixel_rgb(uint32_t format, const uint8_t *pixel, uint8_t *rgb) {
    if (format==DRM_FORMAT_XRGB8888 || format==DRM_FORMAT_ARGB8888) {
        rgb[0]=pixel[2]; rgb[1]=pixel[1]; rgb[2]=pixel[0];
    } else {
        rgb[0]=pixel[0]; rgb[1]=pixel[1]; rgb[2]=pixel[2];
    }
}

static void dump_fb(int fd, uint32_t id, const char *directory) {
    struct drm_mode_fb_cmd2 fb={.fb_id=id};
    if (ioctl(fd,DRM_IOCTL_MODE_GETFB2,&fb)) {
        printf("GETFB2 id=%u error=%s\n",id,strerror(errno)); return;
    }
    printf("FB id=%u size=%ux%u format=0x%08x pitch=%u offset=%u modifier=0x%016" PRIx64 " handle=%u\n",
           id,fb.width,fb.height,fb.pixel_format,fb.pitches[0],fb.offsets[0],
           (uint64_t)fb.modifier[0],fb.handles[0]);
    if (!directory || !fb.handles[0] || !fb.width || !fb.height || fb.width>16384 || fb.height>16384) return;
    if (fb.modifier[0] || (fb.pixel_format!=DRM_FORMAT_XRGB8888 && fb.pixel_format!=DRM_FORMAT_ARGB8888 &&
                         fb.pixel_format!=DRM_FORMAT_XBGR8888 && fb.pixel_format!=DRM_FORMAT_ABGR8888)) {
        puts("Framebuffer is not a supported linear RGB layout; no unsafe decoding attempted."); return;
    }
    uint64_t size=(uint64_t)fb.pitches[0]*fb.height+fb.offsets[0];
    if (fb.pitches[0]<(uint64_t)fb.width*4 || size>128*1024*1024) return;
    struct drm_mode_map_dumb mapping={.handle=fb.handles[0]};
    if (ioctl(fd,DRM_IOCTL_MODE_MAP_DUMB,&mapping)) {
        printf("MAP_DUMB id=%u error=%s\n",id,strerror(errno)); return;
    }
    const uint8_t *memory=mmap(NULL,(size_t)size,PROT_READ,MAP_SHARED,fd,(off_t)mapping.offset);
    if (memory==MAP_FAILED) {printf("mmap read-only: %s\n",strerror(errno));return;}
    char path[512];
    int length=snprintf(path,sizeof(path),"%s/fb-%u.ppm",directory,id);
    if (length<0 || (size_t)length>=sizeof(path)) {munmap((void *)memory,(size_t)size);return;}
    FILE *file=fopen(path,"wb");
    uint8_t *row=malloc((size_t)fb.width*3);
    if (file && row) {
        fprintf(file,"P6\n%u %u\n255\n",fb.width,fb.height);
        uint64_t white=0,black=0,total=(uint64_t)fb.width*fb.height;
        for (uint32_t y=0;y<fb.height;++y) {
            for (uint32_t x=0;x<fb.width;++x) {
                const uint8_t *pixel=memory+fb.offsets[0]+(size_t)y*fb.pitches[0]+(size_t)x*4;
                pixel_rgb(fb.pixel_format,pixel,row+(size_t)x*3);
                if (row[x*3]==255 && row[x*3+1]==255 && row[x*3+2]==255) ++white;
                if (!row[x*3] && !row[x*3+1] && !row[x*3+2]) ++black;
            }
            if (fwrite(row,3,fb.width,file)!=fb.width) {puts("Framebuffer output write failed");break;}
        }
        printf("DUMP %s pixels=%" PRIu64 " white=%" PRIu64 " black=%" PRIu64 "\n",path,total,white,black);
    }
    free(row);
    if (file) fclose(file);
    munmap((void *)memory,(size_t)size);
}

int main(int argc,char **argv) {
    if (argc==2 && !strcmp(argv[1],"--self-test")) {
        uint8_t pixel[]={11,22,33,255},rgb[3];
        pixel_rgb(DRM_FORMAT_XRGB8888,pixel,rgb);
        if (rgb[0]!=33 || rgb[1]!=22 || rgb[2]!=11) return 1;
        pixel_rgb(DRM_FORMAT_XBGR8888,pixel,rgb);
        if (rgb[0]!=11 || rgb[1]!=22 || rgb[2]!=33) return 1;
        puts("DRM query probe: RGB decoding self-test passed; no device opened."); return 0;
    }
    const char *device=argc>1?argv[1]:"/dev/dri/card0";
    const char *directory=argc>2?argv[2]:NULL;
    if (directory && strncmp(directory,"/tmp/sheng-",11)) {fputs("Dump directory must be temporary\n",stderr);return 2;}
    if (directory && mkdir(directory,0755) && errno!=EEXIST) {perror("mkdir");return 2;}
    int fd=open(device,O_RDWR|O_CLOEXEC);
    if (fd<0) {perror(device);return 1;}
    struct drm_set_client_cap cap={.capability=DRM_CLIENT_CAP_UNIVERSAL_PLANES,.value=1};
    if (ioctl(fd,DRM_IOCTL_SET_CLIENT_CAP,&cap)) printf("Client universal planes: %s\n",strerror(errno));
    uint32_t fbs[128]={0},crtcs[128]={0},connectors[128]={0},encoders[128]={0};
    struct drm_mode_card_res resources={.fb_id_ptr=(uintptr_t)fbs,.crtc_id_ptr=(uintptr_t)crtcs,
        .connector_id_ptr=(uintptr_t)connectors,.encoder_id_ptr=(uintptr_t)encoders,
        .count_fbs=128,.count_crtcs=128,.count_connectors=128,.count_encoders=128};
    if (ioctl(fd,DRM_IOCTL_MODE_GETRESOURCES,&resources)) {perror("GETRESOURCES");close(fd);return 1;}
    printf("RESOURCES fbs=%u crtcs=%u connectors=%u encoders=%u\n",
        resources.count_fbs,resources.count_crtcs,resources.count_connectors,resources.count_encoders);
    for (uint32_t i=0;i<resources.count_fbs && i<128;++i) add_fb(fbs[i]);
    for (uint32_t i=0;i<resources.count_crtcs && i<128;++i) {
        struct drm_mode_crtc crtc={.crtc_id=crtcs[i]};
        if (ioctl(fd,DRM_IOCTL_MODE_GETCRTC,&crtc)) {perror("GETCRTC");continue;}
        printf("CRTC id=%u fb=%u valid=%u mode=%s %ux%u refresh=%u\n",crtc.crtc_id,crtc.fb_id,
            crtc.mode_valid,crtc.mode.name,crtc.mode.hdisplay,crtc.mode.vdisplay,crtc.mode.vrefresh);
        add_fb(crtc.fb_id);
    }
    uint32_t planes[128]={0};
    struct drm_mode_get_plane_res plane_res={.plane_id_ptr=(uintptr_t)planes,.count_planes=128};
    if (!ioctl(fd,DRM_IOCTL_MODE_GETPLANERESOURCES,&plane_res)) {
        for (uint32_t i=0;i<plane_res.count_planes && i<128;++i) {
            struct drm_mode_get_plane plane={.plane_id=planes[i]};
            if (ioctl(fd,DRM_IOCTL_MODE_GETPLANE,&plane)) continue;
            printf("PLANE id=%u crtc=%u fb=%u possible=0x%x\n",plane.plane_id,plane.crtc_id,plane.fb_id,plane.possible_crtcs);
            add_fb(plane.fb_id);
        }
    }
    for (unsigned int i=0;i<framebuffer_count;++i) dump_fb(fd,framebuffers[i],directory);
    close(fd);
    return 0;
}
