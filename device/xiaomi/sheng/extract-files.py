#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools/extract-utils'))
#
# SPDX-FileCopyrightText: 2024 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

from extract_utils.file import File
from extract_utils.fixups_blob import (
    BlobFixupCtx,
    blob_fixup,
    blob_fixups_user_type,
)
from extract_utils.fixups_lib import (
    lib_fixups,
    lib_fixups_user_type,
)
from extract_utils.main import (
    ExtractUtils,
    ExtractUtilsModule,
)

namespace_imports = [
    'device/xiaomi/sheng',
    'hardware/qcom-caf/wlan',
    'hardware/qcom-caf/sm8550',
    'hardware/xiaomi',
    'vendor/qcom/opensource/commonsys-intf/display',
    'vendor/qcom/opensource/dataservices',
]

def lib_fixup_vendor_suffix(lib: str, partition: str, *args, **kwargs):
    return f'{lib}-{partition}' if partition == 'vendor' else None


def lib_fixup_sheng_sqlite(lib: str, partition: str, *args, **kwargs):
    # The stock ODM sqlite3.so is a shared library, whereas the platform's
    # sqlite3 module is an executable. Keep the SONAME but give the module an alias.
    return f'{lib}-sheng'


lib_fixups: lib_fixups_user_type = {
    **lib_fixups,
    'sqlite3': lib_fixup_sheng_sqlite,
    (
        'vendor.qti.hardware.qccsyshal@1.0',
        'vendor.qti.hardware.qccsyshal@1.1',
        'vendor.qti.hardware.qccsyshal@1.2',
        'vendor.qti.hardware.qccvndhal@1.0',
        'vendor.qti.imsrtpservice@3.0',
        'vendor.qti.imsrtpservice@3.1',
        'vendor.qti.diaghal@1.0',
    ): lib_fixup_vendor_suffix,
}

blob_fixups: blob_fixups_user_type = {
    'system_ext/lib64/vendor.qti.hardware.qccsyshal@1.2-halimpl.so' : blob_fixup()
        .replace_needed('libprotobuf-cpp-full.so', 'libprotobuf-cpp-full-21.7.so'),
    'odm/lib64/libmt@1.3.so' : blob_fixup()
        .replace_needed('libcrypto.so', 'libcrypto-v33.so'),
    ('vendor/bin/hw/android.hardware.security.keymint-service-qti',
     'vendor/lib64/libqtikeymint.so') : blob_fixup()
        .add_needed('android.hardware.security.rkp-V3-ndk.so'),
    'vendor/etc/seccomp_policy/qwesd@2.0.policy' : blob_fixup()
        .add_line_if_missing('pipe2: 1'),
    'vendor/etc/qcril_database/upgrade/config/6.0_config.sql' : blob_fixup()
        .regex_replace('(persist\\.vendor\\.radio\\.redir_party_num.*)true', '\\1false'),
    'vendor/lib64/libqcodec2_core.so' : blob_fixup()
        .add_needed('libcodec2_shim.so'),
    'vendor/lib64/c2.dolby.client.so': blob_fixup()
        .add_needed('libcodec2_shim.so'),
    # Current LLNDK link stubs expose these stable public APIs unversioned.
    # Bind to the same runtime default exports rather than an old version tag.
    'odm/lib64/libMiPhotoFilter.so': blob_fixup()
        .add_needed('libnativewindow.so')
        .clear_symbol_version('AHardwareBuffer_allocate')
        .clear_symbol_version('AHardwareBuffer_describe')
        .clear_symbol_version('AHardwareBuffer_isSupported')
        .clear_symbol_version('AHardwareBuffer_lockPlanes')
        .clear_symbol_version('AHardwareBuffer_release')
        .clear_symbol_version('AHardwareBuffer_unlock'),
    'odm/lib64/libmorpho_ubwc.so': blob_fixup()
        .add_needed('libnativewindow.so')
        .clear_symbol_version('AHardwareBuffer_describe'),
    'odm/lib64/libTrueSight.so': blob_fixup()
        .add_needed('libnativewindow.so')
        .clear_symbol_version('AHardwareBuffer_allocate')
        .clear_symbol_version('AHardwareBuffer_describe')
        .clear_symbol_version('AHardwareBuffer_lock')
        .clear_symbol_version('AHardwareBuffer_lockPlanes')
        .clear_symbol_version('AHardwareBuffer_release')
        .clear_symbol_version('AHardwareBuffer_unlock'),
    'odm/lib64/libwrapper_dlengine.so': blob_fixup()
        .add_needed('liblog.so'),
    'odm/lib64/libcrussp.so': blob_fixup()
        .add_needed('libsheng_audio_log_compat.so'),
    (
        'odm/lib64/hw/camera.xiaomi.so',
        'odm/lib64/hw/com.qti.chi.override.so',
        'odm/lib64/libchifeature2.so',
        'odm/lib64/libmialgoengine.so',
    ): blob_fixup()
        .add_needed('libprocessgroup_shim.so'),
    'vendor/lib64/vendor.libdpmframework.so' : blob_fixup()
        .add_needed('libhidlbase_shim.so'),
    (
        'vendor/bin/hw/android.hardware.contexthub-service.qmi',
        'vendor/lib64/libstfactory-vendor.so',
        'odm/lib64/nfc_nci.nqx.default.hw.so'
    ): blob_fixup()
        .add_needed('libbase_shim.so'),
    (
       'vendor/etc/media_codecs_kalama.xml',
    ): blob_fixup()
        .regex_replace('.+media_codecs_(google_audio|google_c2|google_telephony|vendor_audio).+\n', ''),
    (
        'vendor/bin/poweropt-service',
        'vendor/lib64/libaodoptfeature.so',
        'vendor/lib64/libdpps.so',
        'vendor/lib64/libpowercore.so',
        'vendor/lib64/libpsmoptfeature.so',
        'vendor/lib64/libsnapdragoncolor-manager.so',
        'vendor/lib64/libstandbyfeature.so',
        'vendor/lib64/libvideooptfeature.so',
    ): blob_fixup()
        .replace_needed('libtinyxml2.so', 'libtinyxml2-v34.so'),
    'vendor/etc/init/hw/init.batterysecret.rc' : blob_fixup()
        .regex_replace('group system system wakelock', 'group system system usb wakelock'),
}  # fmt: skip
# The supplied sheng package has malformed XML declarations in these files.
blob_fixups.update({
    ('odm/etc/camera/enhance_motiontuning.xml',
     'odm/etc/camera/night_motiontuning.xml',
     'odm/etc/camera/motiontuning.xml'): blob_fixup()
        .regex_replace(r'<\?xml=version=', '<?xml version='),
})
module = ExtractUtilsModule('sheng', 'xiaomi', blob_fixups=blob_fixups,
    lib_fixups=lib_fixups, namespace_imports=namespace_imports)
if __name__ == '__main__':
    ExtractUtils.device(module).run()
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'tools'))
    from postprocess_vendor import postprocess_vendor
    postprocess_vendor(Path(__file__).resolve().parents[3] / 'vendor/xiaomi/sheng')
