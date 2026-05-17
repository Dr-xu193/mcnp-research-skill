# Original Files

This folder contains the original standalone script for users who do not want to use the packaged `mcnp_research_skill` workflow.

中文说明：这个文件夹是“原始文件”备用入口。它不是 skill 的一部分，也不会被 `mcnp_research_skill` CLI 自动调用。

## Files

| File | Purpose |
|---|---|
| `auto.py` | Original Tkinter GUI script from the legacy workflow. |

## How to run

From this folder:

```powershell
python auto.py
```

This starts the original GUI program directly.

## Relationship to the skill

`auto.py` is provided only as an alternative for users who prefer the original Python GUI script.

It is intentionally separate from the skill package:

- not imported by `mcnp_research_skill`
- not used by the CLI
- not included in package data
- not part of the AI workflow planner
- not covered by the release-hardening guarantees of the new skill

Use the main skill workflow if you want structured planning, diagnostics, dry-run safety, runtime preflight, JSON output, and CI-tested behavior.

Use `auto.py` if you want the older all-in-one GUI behavior and are willing to configure the environment manually.

## Environment requirements

Recommended environment:

- Windows
- Python 3.x
- Tkinter, usually included with standard Python installers
- `numpy`
- `pandas`
- `scipy`
- `matplotlib`
- MCNP5 / MCNP5 MPI executable, for example `mcnp5mpi.exe`
- MPICH/OpenMPI launcher, for example `mpirun` or `mpiexec`
- Optional: Origin + `pywin32` if using Origin automation

Install common Python dependencies:

```powershell
python -m pip install numpy pandas scipy matplotlib
```

For Origin automation on Windows:

```powershell
python -m pip install pywin32
```

## MCNP / MPI command note

The original GUI may show a default command similar to:

```powershell
mpirun -np 17 mcnp5mpi.exe
```

This is only an example from the original local environment. Users must adjust it for their own machine.

The `-np` value depends on local CPU resources and the user's MPI/MCNP setup. A common policy used in the legacy workflow is logical processors + 1, but this is not an MPI standard.

## Important limitations

- This script can run real MCNP/MPI if the user clicks the corresponding GUI actions.
- There is no `--execute --confirm-user` gate like the packaged skill.
- Some paths, detector reference points, source assumptions, GEB assumptions, and Origin behavior may be legacy-specific.
- It may need manual editing for each user's workstation.
- It is not a substitute for validating MCNP input files under MCNP5_RSICC 1.14.

## Safety boundary

This repository does not provide MCNP downloads, cracks, licenses, or authorization-bypass instructions. Users must provide their own legally available MCNP installation and configure MPICH/OpenMPI locally.
