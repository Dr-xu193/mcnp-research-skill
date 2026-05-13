# mcnp_research_skill

`mcnp_research_skill` 是从 `legacy/auto.py` 拆分出的 MCNP5 探测器效率刻度工具包。当前阶段保留原物理计算逻辑，核心模块返回结构化 dict，外部副作用默认 `dry_run`。

## Capabilities

- MCNP 输入生成：`mcnp_input.generator.generate_mcnp_inputs`
- MPI 批处理：`mcnp_run.mpi_runner.run_mpi_batch`
- MCNP 输出 CSV 提取：`mcnp_output.tally_extractor.extract_tally_csvs`
- 能谱绘图：`spectra.plotter.plot_spectra`
- GEB/CSV 分析：`geb.analyzer.run_geb_csv_analysis`
- SPE 反推 GEB：`geb.spe.fit_geb_from_spe_files`
- Origin OPJ 导出：`origin.origin_exporter.export_origin_projects`

## Safety Defaults

- 不修改 `auto.py` 和 `legacy/auto.py`。
- 默认 dry-run。
- MPI 真实运行必须使用 `--execute --confirm-mpi`。
- Origin 真实运行必须使用 `--execute --confirm-origin`。
- Origin 不进入默认 pipeline。
- CLI 输出 ASCII-safe JSON。

## Core CLI

```powershell
python -m mcnp_research_skill.cli generate-inputs --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli run-mpi --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli extract-csv --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli plot-spectra --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli run-core-pipeline --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli fit-geb-from-spe --spe file1.spe --spe file2.spe
python -m mcnp_research_skill.cli origin-export --target-dir D:/MCNP/work --dry-run
```

## Verification

```powershell
python -m compileall -q mcnp_research_skill tests
python -m pytest -q
```

See `docs/FINAL_CHECKLIST.md` for dry-run acceptance and real MPI/Origin pre-run checklists.
