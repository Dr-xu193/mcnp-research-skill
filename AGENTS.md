# MCNP Research Skill Agent Guide

## Project Role

本项目是从 `legacy/auto.py` 拆分出的 MCNP Research Skill 工具包，用于：

- MCNP 输入生成
- MPI 批处理 dry-run/确认执行
- MCNP 输出 CSV 提取
- 能谱绘图
- GEB/CSV 分析
- SPE 反推 GEB 参数
- Origin OPJ 导出 dry-run/确认执行

## Code Maintenance Rules

- 不要修改 `auto.py` 和 `legacy/auto.py`。
- 不要改变物理算法；迁移、封装、测试可以做，物理计算逻辑不能擅自重写。
- 不要把 GUI 逻辑写入核心模块；核心模块不能依赖 tkinter、messagebox 或控件状态。
- 核心函数必须返回结构化 dict，包含 `ok`、`warnings`、`errors` 等可机器检查字段。
- 所有外部副作用必须支持 `dry_run`。
- 新增功能必须先有测试，再实现。
- CLI 输出必须保持 ASCII-safe JSON，避免 Windows 控制台编码问题。
- README、docs、tests 可以维护；核心业务代码变更必须有明确阶段要求。

## Safety Rules

- 默认使用 `dry_run`。
- MPI 真实运行必须显式使用 `--execute --confirm-mpi`。
- Origin 真实运行必须显式使用 `--execute --confirm-origin`。
- 不要自动删除用户文件；清理行为必须限定在模块约定的临时文件和确认路径内。
- 不要自动覆盖 legacy 文件，尤其不要覆盖 `auto.py` 或 `legacy/auto.py`。
- 不要在测试中真实调用 MCNP、mpirun、Origin、win32com。
- 不要在核心模块中使用 tkinter、messagebox、print。
- 不要把 Origin 加入默认 pipeline；Origin 只作为独立 dry-run/确认执行工具。

## Common Commands

```powershell
python -m compileall -q mcnp_research_skill tests
python -m pytest -q
python -m mcnp_research_skill.cli run-core-pipeline --config configs/example.pipeline.yaml --dry-run
python -m mcnp_research_skill.cli fit-geb-from-spe --spe file1.spe --spe file2.spe
python -m mcnp_research_skill.cli origin-export --target-dir D:/MCNP/work --dry-run
```

## Current Boundaries

- MCP 暂不做。
- GUI 暂不重接入。
- Origin 不进入默认 pipeline。
- `legacy/auto.py` 是迁移基准，只读保留。
