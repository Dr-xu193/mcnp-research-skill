# Model Card: nai_1x1_template

## Status

- **Model id**: `nai_1x1_template`
- **Display name**: 1x1 NaI(Tl) unverified template
- **Status**: template / unverified
- **Source basis**: nominal 1 inch diameter x 1 inch length NaI(Tl) dimensions and simplified material assumptions recorded in the registry.

This model is not a verified detector model. It is a starter template that must be checked against the user's actual detector datasheet, housing, window, reflector, PMT, and measurement geometry.

## Intended use

Use this model only when the user needs a 1-inch NaI starter deck and understands that it is not verified.

The AI/user interface must clearly state that this model requires user validation before real analysis.

## Template reference points

| Reference point | Position cm | Basis | Verified |
|---|---:|---|:---:|
| `nai_crystal_front_surface` | `[0.0, 0.0, 0.0]` | template coordinate convention | no |
| `nai_crystal_center` | `[0.0, 0.0, 1.27]` | template dimension: 1 inch length | no |
| `aluminum_shell_front` | `[0.0, 0.0, -0.1]` | template assumption: 0.1 cm Al front window | no |

## Main assumptions

- 1 inch = 2.54 cm.
- Crystal radius is 1.27 cm.
- Crystal length is 2.54 cm.
- Aluminum housing/window thickness is assumed as 0.1 cm.
- Materials are simplified from the verified 3x3 fixture conventions.
- No PMT, reflector, optical window, rear structure, or manufacturer-specific packaging is represented.
- z=0 is a coordinate convention, not a measured surface.

## Safety boundaries

- Do not call this model verified.
- Do not assume the template reference points match a real detector without user confirmation.
- Do not use this model for final efficiency calibration unless the user has validated geometry and materials.
- Do not silently alter geometry/material/source/tally physics to “fix” user requests.

## Recommended user-facing warning

“`nai_1x1_template` 是未验证模板。它可以用于生成和测试 workflow，但实际探测器几何、铝窗厚度、外壳、反射层和 PMT 结构需要用户根据自己的探测器资料验证。”
