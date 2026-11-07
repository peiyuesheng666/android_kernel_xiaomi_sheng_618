# OEM GraphicBuffer allocation compatibility

The factory camera libraries and Dolby video libraries allocate 256-byte
GraphicBuffer objects. The current vendor libui appends DependencyMonitor and
requires 3376 bytes. The camera provider's user-triggered crash is in that new
member's destruction. An isolated libui probe confirms writes beyond byte 256,
and 200 construction/destruction cycles with current-sized storage keep both
redzones intact. No camera HAL or image acquisition is involved in that probe.

The transform changes only fourteen reviewed `mov w0, #256` allocation-size
instructions in seven exact inputs. It keeps all addresses, relocations,
dynamic dependencies, constructors, destructors and other bytes intact. The
two decoder inputs retain the separately reviewed r24 AHandler symbol routing.
The platform-built libgui_vendor already uses current headers and is excluded.

A non-installable vendor archive records sizeof(GraphicBuffer). Every generated
library depends on that archive; only the reviewed 256- and 3376-byte layouts
and the checked public prefix are accepted. No shared libui, platform source,
camera-provider lifecycle, permissions or SELinux rules are changed.

`stock/` contains the unchanged factory camera, grallocutils, mawutils,
vidhance and encoder inputs. Their hashes and reviewed virtual addresses are
pinned in patch.py. Existing device-owned decoder filegroups supply the other
two inputs. Generated vendor installers retain their original module names
and destinations. The archive and patch tool are build inputs only.

Evidence: workspace reports/device/r24-investigation/camera-* and
graphicbuffer-abi-probe-r25.txt, followed by reports/device/r25-investigation.
Successful generation or empty-object tests do not establish working camera
preview, image processing, DRM, or real Dolby video-stream decoding.
