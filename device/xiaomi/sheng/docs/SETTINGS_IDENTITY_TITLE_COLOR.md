# Settings identity title color

The user observed grey titles for Model name and Device codename after r29.
The pinned AndroidX Preference 1.3.0-alpha01 source, Preference.java lines 537–540,
explicitly copies the summary color onto the title when a preference is enabled
but not selectable. Both sheng identity rows set android:selectable=false.

Set those two rows selectable in both pages and both locale variants. They retain
no click listener, fragment or intent, so tapping does not navigate or change any
identity. Long-press copying is retained. The platform now keeps its ordinary
title color; no literal black color is introduced, so dark themes remain legible.
The native model controller, summaries and all external resource IDs are retained.
No Settings source, framework source or SystemUI change is needed.

The ResourceProbe checks the actual compiled XML selectable flag in addition to
both labels, summaries, controller counts and external references. Final color
appearance remains subject to user acceptance after installation.

r30 was installed on ca10ede3 slot b on 2026-11-08. The user confirmed both
titles now have the normal color. Seven partition hashes, the installed overlay
hash, original SystemUI and installed Chinese/English resource probes passed;
the crash buffer was empty. See runtime-r30-identity-titles-20261108.json.
This scoped overlay build does not establish a full product build result.
