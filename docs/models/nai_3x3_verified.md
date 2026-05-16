# Model Card: nai_3x3_verified

## Status

- **Model id**: `nai_3x3_verified`
- **Display name**: 3x3 NaI(Tl) verified deck
- **Status**: verified
- **Source**: A.txt fixture copied into `mcnp_research_skill/models/fixtures/nai_3x3_verified.txt`

This is currently the only verified built-in NaI model.

## Intended use

Use this model when the user asks for a 3-inch NaI(Tl) detector workflow and does not provide a custom MCNP deck.

Supported workflows include:

- deck inspection
- MCNP5 diagnostics
- point source sweep
- disk source sweep
- F8 CSV/plot postprocess
- FT8 GEB patching
- run failure analysis context

## Verified reference points

| Reference point | Position cm | Basis | Verified |
|---|---:|---|:---:|
| `nai_crystal_front_surface` | `[0.0, 0.0, 0.0]` | derived from A.txt surface 14 `pz 0` | yes |
| `nai_crystal_center` | `[0.0, 0.0, 3.81]` | derived from A.txt crystal z range 0 to 7.62 | yes |
| `aluminum_shell_front` | `[0.0, 0.0, -0.34]` | derived from A.txt surface 11 `pz -0.340` | yes |

## Known tally and source characteristics

The registered source description records the deck as an encapsulated Am-241 disk-source style deck with TR1 translation and an F8 pulse-height tally on crystal cell 104.

The workflow may preserve the existing source, replace it with a point source, or create a `disk_tr1` source depending on the requested source strategy.

## Safety boundaries

- Do not silently modify geometry, material definitions, tally physics, or source physics.
- If the user asks for “晶体表面” or “距离探测器” without a precise reference point, ask them to choose a canonical reference point.
- When applying GEB, patch only `FT8 GEB` and only when F8 exists.
- Run `diagnose-deck` after patching before confirmed execution.

## Not covered

This model card does not claim validation of detector efficiency against measurement data. It only documents the built-in deck source and reference-point basis used by the skill.
