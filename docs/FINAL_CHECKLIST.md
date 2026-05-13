# Final Acceptance Checklist

## Completed Modules

- `mcnp_research_skill.spectra`: CSV spectrum loading, linear/log plotting, spectra CLI.
- `mcnp_research_skill.mcnp_input`: MCNP input generation with source cards, NPS, TR1, composite sources, GEB card handling, and `dry_run`.
- `mcnp_research_skill.mcnp_output`: F8 tally CSV extraction to `*_Data.csv`.
- `mcnp_research_skill.mcnp_run`: MPI batch dry-run and confirmed execution guard.
- `mcnp_research_skill.pipeline`: core pipeline orchestration for generate, MPI, CSV extraction, and spectra plotting.
- `mcnp_research_skill.cli`: top-level ASCII-safe JSON CLI.
- `mcnp_research_skill.geb`: CSV GEB analysis, efficiency calculation, report generation, and SPE-based GEB fitting.
- `mcnp_research_skill.origin`: Origin OPJ export dry-run and confirmed execution isolation.

## Not Done By Design

- MCP 暂不做。
- GUI 暂不重接入。
- Origin 不进默认 pipeline。
- `auto.py` 和 `legacy/auto.py` 保持只读基准状态。

## Final Test Commands

```powershell
python -m compileall -q mcnp_research_skill tests
python -m pytest -q
```

## Dry-run Acceptance

1. 准备一个包含 `base_file`、`output_dir`、`mpi_command` 和 `plot_output` 的 pipeline config。
2. 运行：

```powershell
python -m mcnp_research_skill.cli run-core-pipeline --config configs/example.pipeline.yaml --dry-run
```

3. 检查 JSON：
   - `dry_run` 为 `true`。
   - 每个步骤在 `steps` 中保留结果。
   - MPI 只返回 planned commands，不生成 `i.txt`、`o.txt`。
   - plot 只返回计划，不写 PNG。
4. 确认工作目录没有新增真实运行产物。

## Real MPI Pre-run Checklist

- 已人工检查 base deck、距离、reference point、NPS、energy/composite source。
- 已运行 generate-inputs dry-run 并确认 planned files。
- 已运行 run-mpi dry-run 并确认数字输入文件顺序、命令、预计输出名。
- 已确认 `mpi_command` 指向正确的 MCNP5 MPI 可执行环境。
- 已确认 target_dir 是可写工作目录，不是 legacy 目录。
- 已确认可以接受 `i.txt`、`o.txt`、runt/mesch/comou/mdata 临时文件清理。
- 真实执行命令必须包含：

```powershell
python -m mcnp_research_skill.cli run-mpi --config configs/example.pipeline.yaml --execute --confirm-mpi
```

## Real Origin Pre-run Checklist

- 已运行 origin-export dry-run 并确认 planned `.opj` 路径。
- 已确认 target_dir 下的 `*_Data.csv` 文件正确。
- 已确认 Windows 上安装了 Origin 和 pywin32。
- 已保存其他 Origin 工作，接受自动关闭 Origin 进程的风险。
- 已确认 `temp_workspace` 不包含需要保留的用户文件。
- 真实执行命令必须包含：

```powershell
python -m mcnp_research_skill.cli origin-export --target-dir D:/MCNP/work --execute --confirm-origin
```

## Share With Another User

1. 提供整个项目目录，保留 `mcnp_research_skill/`、`configs/`、`tests/`、`docs/`、`AGENTS.md` 和 `.agents/skills/mcnp-research-pipeline/SKILL.md`。
2. 说明 `auto.py` 和 `legacy/auto.py` 是迁移基准，不应覆盖。
3. 让对方先运行最终测试命令。
4. 让对方复制并修改 `configs/example.pipeline.yaml`，先执行 dry-run。
5. 真实 MPI 或 Origin 操作前按本清单逐项确认。
