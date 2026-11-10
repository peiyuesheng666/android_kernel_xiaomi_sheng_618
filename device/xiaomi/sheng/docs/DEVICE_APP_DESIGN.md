# Device-owned application design

User requirements recorded on 2026-11-10 apply to Dolby, future FaceUnlock and
other device repair/settings applications developed in this tree.

- Match the installed system Settings appearance. Use dynamic Monet colors for
  backgrounds, surface containers, text, selected controls and disabled states;
  provide matching light/dark themes rather than hardcoded neutral surfaces.
- Use modern large, rounded switches and buttons, with consistent profile
  selectors and sliders. Preserve touch targets, keyboard navigation, checked
  state accessibility, disabled state and feedback.
- Use simple, recognizable icons with a monochrome/themed representation. Dolby
  uses the familiar opposing double-D silhouette referenced from Dolby's site.
- Formal utilities have a Settings entry and no launcher intent filter.
  Preserve explicitly requested audio-effect entry points and service operation.
  Test applications may retain a launcher entry for user-operated validation.
- The final face implementation is named **FaceUnlock**. ShengFaceLab is only
  the current testing application; it has not implemented accepted system unlock.
- Our application source participates in the normal Soong product build, then
  its output is preinstalled in the image. Incremental builds reuse unchanged
  outputs. Separately scoped APK builds are development evidence, not evidence
  that a full product/normal module build has passed.

Keep implementation under device/xiaomi/sheng and preserve original SystemUI.
Use reference ROMs as design evidence, without transplanting their applications.
