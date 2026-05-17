# MCNP Research Skill — v0.4.0-beta

`mcnp_research_skill` 是一个面向 MCNP5 工作流的研究型 AI skill / CLI 工具包，从 `legacy/auto.py` 重构而来。

当前版本重点能力：自然语言 workflow、MCNP5_RSICC 1.14 输入诊断、guided repair、NaI(Tl) 内置模型、命名参考点、runtime preflight、运行失败分析、F8/非 F8 边界说明，以及 SPE 拟合 GEB 并写入 FT8 GEB 的工作流。

**748 tests，GitHub Actions 绿色，测试不真实运行 MCNP/MPI。**

## 安装

```powershell
python -m pip install -e .
```

安装后使用：

```powershell
python -m mcnp_research_skill.cli --help
```

## 用户入口

默认输出中文说明，`--json` 切换为结构化 JSON。

```powershell
# 1. 自然语言 → 结构化计划
python -m mcnp_research_skill.cli plan-request `
  --text "用3英寸NaI，Cs-137点源，距离NaI晶体前表面10到20厘米，每步5厘米，NPS=1e6，只出CSV"

# 2. 保存计划
python -m mcnp_research_skill.cli plan-request `
  --text "用2英寸NaI，距离铝壳表面10到20厘米每步5厘米，Cs-137，NPS=1e7，只出CSV" `
  --output plan.json

# 3. 执行计划（dry-run 默认）
python -m mcnp_research_skill.cli execute-plan --plan-file plan.json

# 4. 环境检查
python -m mcnp_research_skill.cli runtime-check

# 5. MCNP5 输入诊断
python -m mcnp_research_skill.cli diagnose-deck --input A.txt

# 6. 运行失败分析
python -m mcnp_research_skill.cli analyze-run-failure --output o.txt
```

## 两步式交互

```text
自然语言请求
  → plan-request（中文输出理解 + 映射 + 缺参数提示）
  → 用户确认
  → execute-plan（dry-run 或 --execute --confirm-user）
  → runtime-check（检测 MCNP/MPICH 就绪状态）
  → 如果失败 → analyze-run-failure（output 前 300 行分析 + 建议）
```

## 安全门槛

| 条件 | 说明 |
|------|------|
| 默认模式 | **dry-run**，不执行 MCNP |
| 真实执行 | `--execute --confirm-user` 二者缺一不可 |
| MCNP 不存在 | 提示安装合法授权 MCNP，不提供下载/破解 |
| MPI 不存在 | 提示安装 MPICH/OpenMPI |
| 推荐 NP | `os.cpu_count() + 1`，auto.py 兼容策略，不是 MPI 标准 |

## 内置模型

| 模型 | 状态 | 参考点 | Model card |
|------|------|--------|------------|
| `nai_3x3_verified` | **已验证**（A.txt 副本） | 铝壳前 / 晶体中心 / 晶体前（来自 A.txt 几何） | `docs/models/nai_3x3_verified.md` |
| `nai_2x2_template` | 未验证模板 | 铝壳前 / 晶体中心 / 晶体前（模板假设，用户必须验证） | `docs/models/nai_2x2_template.md` |
| `nai_1x1_template` | 未验证模板 | 同上 | `docs/models/nai_1x1_template.md` |

```powershell
python -m mcnp_research_skill.cli models list
python -m mcnp_research_skill.cli models inspect nai_3x3_verified
```

## Release 文档

| 文档 | 用途 |
|------|------|
| `docs/ai_usage_contract.md` | AI 调用规则、文件角色判断、安全执行边界 |
| `docs/error_codes.md` | 错误码、中文含义、blocking / auto-fixable / 用户下一步 |
| `docs/real_mcnp_validation.md` | 用户本地真实 MCNP/MPICH 手动验收流程 |
| `docs/release_v0.4.0_beta.md` | v0.4.0-beta 发布说明 |
| `docs/final_freeze_checklist.md` | 最终冻结检查清单 |

## 三类参考点

| 标准名称 | 中文 |
|----------|------|
| `aluminum_shell_front` | 铝壳前表面 |
| `nai_crystal_front_surface` | 碘化钠晶体前端表面 |
| `nai_crystal_center` | 碘化钠晶体中心 |

歧义别名（例如“晶体表面”“距离探测器”）返回 `AMBIGUOUS_REFERENCE_POINT`，提示用户明确选择。

## 源策略

| 策略 | 说明 |
|------|------|
| `point_sdef_pos` | 点源（`sdef pos=X Y Z par=2 erg=E`），sweep 默认 |
| `disk_tr1` | 圆面源（`trN + sdef rad=dN + siN/spN`），需要 `source_radius` |
| `preserve_existing_source` | 保留源项，只改 NPS |

## Sweep 自动化

```powershell
python -m mcnp_research_skill.cli prepare-point-sweep `
  --builtin-model nai_3x3_verified `
  --start 10 --stop 20 --step 5 `
  --reference-point nai_crystal_front_surface `
  --source-energy 0.662 --nps 1e6

python -m mcnp_research_skill.cli prepare-disk-sweep `
  --builtin-model nai_2x2_template `
  --start 10 --stop 20 --step 5 `
  --reference-point aluminum_shell_front `
  --source-energy 0.662 --source-radius 0.15 --nps 1e7
```

## MCNP5_RSICC 1.14 诊断与修复

```powershell
python -m mcnp_research_skill.cli diagnose-deck --input A.txt --mcnp-version mcnp5_rsicc_1_14
python -m mcnp_research_skill.cli repair-deck --input A.txt --output fixed.txt
```

检查重点包括：80 列限制、tab、continuation、comment card、中文注释、non-ASCII title/data card、cell/surface/material/tally/source 引用问题。

`repair-deck` 只修安全格式问题，不自动修改几何布尔表达式、F card、material 或 source physics。

## 运行失败分析

```powershell
python -m mcnp_research_skill.cli analyze-run-failure `
  --output o.txt --stderr e.txt --context plan.json
```

- 默认优先分析 output **前 300 行**，不展示完整几万行日志
- 前部无法判断时才 fallback 到 stderr/stdout/tail 摘要
- 结合模型、源策略、tally、postprocess 意图给中文建议

## SPE → GEB → FT8 GEB

```powershell
# 从 SPE 拟合 GEB A/B/C
python -m mcnp_research_skill.cli fit-geb-from-spe `
  --spe Cs137.spe --spe Co60.spe --spe Am241.spe `
  --profile geb_profile.yaml

# 已知 A/B/C 时写入 FT8 GEB
python -m mcnp_research_skill.cli patch-deck `
  --input A.txt --output A_geb.txt --geb -0.01 0.05 0.2

# SPE 拟合后写入 deck，不覆盖原始输入
python -m mcnp_research_skill.cli fit-geb-and-patch-deck `
  --input A.txt --output A_geb.txt `
  --spe Cs137.spe --spe Co60.spe --spe Am241.spe
```

边界：GEB 只写入 F8 pulse-height tally 的 `FT8 GEB`。非 F8 deck 可以 run-only，但不能写入 FT8 GEB，也不能做 F8 CSV/plot 后处理。

## NPS vs Bq

- `--nps` 是 MCNP histories
- “源强度 1e7” → 可解释为 NPS，但会带 `SOURCE_STRENGTH_INTERPRETED_AS_NPS` warning
- “活度 1e6 Bq” → `ACTIVITY_NORMALIZATION_UNSUPPORTED`，不映射为 NPS

## F8 与非 F8

| 能力 | F8 | F2/F4/F5/F6/FMESH |
|------|:--:|:--:|
| inspect / diagnose / prepare / run / sweep | ✓ | ✓ |
| CSV 提取 / 绘图 | ✓ | ✗ |
| FT8 GEB 写入 | ✓ | ✗ |

非 F8 + CSV/plot 返回 `CSV_REQUIRES_F8`。非 F8 + run-only 正常继续。

## 分支

| 分支 | 用途 |
|------|------|
| `main` | 当前稳定代码 |
| `feature/profiles-init` | 开发分支 |
| `legacy-v0.1` | 旧 main 备份 |
| `codex/v0.2-research-tooling` | v0.2 历史分支 |

## 验证

```powershell
python -m pytest -q                    # 748 passed
python -m mcnp_research_skill.cli --help
```

## 限制

- 不真实运行 MCNP/MPI 测试
- 不提供 MCNP 下载、破解或授权绕过
- 不支持 activity-to-count-rate 归一化（Bq → NPS）
- F2/F4/F5/F6/FMESH 后处理未实现
- NL planner 是 deterministic rule-based parser，不是 LLM
- 1x1/2x2 模型是 unverified template，不是 verified detector model
- 不改 legacy GUI / Origin / SPE / input generator
