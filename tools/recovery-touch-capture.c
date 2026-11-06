// Observe the sheng touch panel without closing DRM or sending gestures to menus.
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static void stop_capture(int signal_number) {
  (void)signal_number;
  stopping = 1;
}

int main(void) {
  char name[256] = {0};
  struct input_absinfo x_range, y_range;
  int fd = open("/dev/input/event5", O_RDONLY | O_NONBLOCK | O_CLOEXEC);
  if (fd < 0) { perror("open touch"); return 1; }
  if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) < 0 ||
      strcmp(name, "NVTCapacitiveTouchScreen") != 0 ||
      ioctl(fd, EVIOCGABS(ABS_MT_POSITION_X), &x_range) < 0 ||
      ioctl(fd, EVIOCGABS(ABS_MT_POSITION_Y), &y_range) < 0) {
    fprintf(stderr, "Unexpected touch device: %s\n", name);
    close(fd);
    return 2;
  }
  if (ioctl(fd, EVIOCGRAB, 1) < 0) { perror("grab touch"); close(fd); return 3; }
  signal(SIGTERM, stop_capture);
  signal(SIGINT, stop_capture);
  signal(SIGHUP, stop_capture);
  setvbuf(stdout, NULL, _IOLBF, 0);
  printf("GRABBED %s x=%d..%d y=%d..%d; menu cannot receive gestures\n",
         name, x_range.minimum, x_range.maximum, y_range.minimum, y_range.maximum);
  struct timespec start, now;
  clock_gettime(CLOCK_MONOTONIC, &start);
  int slot = 0, tracking = -1, x = -1, y = -1;
  struct pollfd wait_fd = { .fd = fd, .events = POLLIN };
  while (!stopping) {
    clock_gettime(CLOCK_MONOTONIC, &now);
    if (now.tv_sec - start.tv_sec >= 180) break;
    int ready = poll(&wait_fd, 1, 250);
    if (ready < 0) { if (errno == EINTR) continue; perror("poll"); break; }
    if (ready == 0) continue;
    struct input_event events[64];
    ssize_t bytes = read(fd, events, sizeof(events));
    if (bytes < 0) { if (errno == EAGAIN || errno == EINTR) continue; perror("read"); break; }
    if (bytes == 0) break;
    for (size_t i = 0; i < (size_t)bytes / sizeof(events[0]); ++i) {
      struct input_event *event = &events[i];
      if (event->type == EV_ABS && event->code == ABS_MT_SLOT) slot = event->value;
      if (slot == 0 && event->type == EV_ABS) {
        if (event->code == ABS_MT_POSITION_X) x = event->value;
        if (event->code == ABS_MT_POSITION_Y) y = event->value;
        if (event->code == ABS_MT_TRACKING_ID) tracking = event->value;
      }
      if (event->type == EV_SYN && event->code == SYN_REPORT) {
        printf("%ld.%06ld id=%d x=%d y=%d\n", (long)event->time.tv_sec,
               (long)event->time.tv_usec, tracking, x, y);
      }
    }
  }
  ioctl(fd, EVIOCGRAB, 0);
  close(fd);
  puts("RELEASED touch input; menu active");
  return 0;
}
