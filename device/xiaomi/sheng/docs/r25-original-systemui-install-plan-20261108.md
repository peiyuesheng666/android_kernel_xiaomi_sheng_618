# r25 supplemental installation review

The sealed r25 ODM/vendor/root-vbmeta images remain unchanged. Their original
review assumed r24 system_ext. After the user prohibited SystemUI changes,
review_sheng_r25_restored_chain.py independently checked the seven pinned images,
parent signatures, three changed/preserved child trees, unchanged root
descriptors and the accepted r22 system-parent key against the r25 root chain.
The supplemental receipt is r25-restored-chain-20261108.json. The unchanged
system descriptor matches r24; accepted system_ext matches its r22 parent.

The first review attempt used avbtool verify_image on a standalone parent. That
command requires absent sibling boot images and failed without changing any
image. The completed review verifies all seven embedded vbmeta signatures
directly, verifies ODM/vendor/system_ext trees with avbtool, and compares the
relevant parent descriptors explicitly. This does not claim revalidation of
unchanged boot/recovery partitions.

The flash helper now requires the supplemental receipt and the exact accepted
six-partition live baseline. It checks the original SystemUI APK hash before
rebooting and writes only odm_b, vendor_b and vbmeta_b on ca10ede3. The matching
runtime verifier requires original SystemUI and restored r22 system_ext and
vbmeta_system. No SystemUI APK, overlay, recovery, data or other tablet is part
of the write scope. Local PowerShell parsing and no-Flash validation passed.
Windows/WSL copies of the modified files were compared before committing.

Runtime camera preview remains untested. The earlier Dolby startup abort and
QTI c2audio SIGSYS remain unresolved; r25's allocation repair does not establish
a fix for either startup failure. Runtime verification must still report any
crash found after boot rather than discarding it.
