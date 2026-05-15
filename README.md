# MCNP Research Skill — v0.3.0

`mcnp_research_skill` 是一个 MCNP5 研究工具包，从 `legacy/auto.py` 重构而来。
支持从自然语言到执行确认的完整 workflow，包含 MCNP5 兼容性诊断、guided repair、
三类 NaI(Tl) 内置模型、命名参考点解析、runtime preflight、failure analysis
等能力。**712 tests，零 MCNP/MPI 真实运行。**

## 安装

```powershell
python -m pip install -e .
```

安装后使用：

```powershell
python -m mcnp_research_skill.cli --help
```

## 用户入口（v0.3.0）

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

```
自然语言请求
  → plan-request（中文输出理解 + 映射 + 缺参数提示）
  → 用户确认
  → execute-plan（dry-run 或 --execute --confirm-user）
  → runtime-check（检测 MCNP/MPICH 就绪状态）
  → 如果失败 → analyze-run-failure（输出前 300 行分析 + 建议）
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

| 模型 | 状态 | 参考点 |
|------|------|--------|
| `nai_3x3_verified` | **已验证**（A.txt 副本） | 铝壳前 / 晶体中心 / 晶体前（全部来自 A.txt 几何） |
| `nai_2x2_template` | 未验证模板 | 铝壳前 / 晶体中心 / 晶体前（模板假设，用户必须验证） |
| `nai_1x1_template` | 未验证模板 | 同上 |

```powershell
python -m mcnp_research_skill.cli models list
python -m mcnp_research_skill.cli models inspect nai_3x3_verified
```

## 三类参考点

| 标准名称 | 中文 |
|----------|------|
| `aluminum_shell_front` | 铝壳前表面 |
| `nai_crystal_front_surface` | 碘化钠晶体前端表面 |
| `nai_crystal_center` | 碘化钠晶体中心 |

歧义别名（"晶体表面""距离探测器"）返回 `AMBIGUOUS_REFERENCE_POINT`，提示用户明确选择。

## 源策略

| 策略 | 说明 |
|------|------|
| `point_sdef_pos` | 点源（sdef pos=X Y Z par=2 erg=E），sweep 默认 |
| `disk_tr1` | 圆面源（trN + sdef rad=dN + siN/spN），需要 source_radius |
| `preserve_existing_source` | 保留源项，只改 NPS |

## Sweep 自动化

```powershell
# 点源 sweep，使用内置模型 + 命名参考点
python -m mcnp_research_skill.cli prepare-point-sweep `
  --builtin-model nai_3x3_verified `
  --start 10 --stop 20 --step 5 `
  --reference-point nai_crystal_front_surface `
  --source-energy 0.662 --nps 1e6

# 面源 sweep
python -m mcnp_research_skill.cli prepare-disk-sweep `
  --builtin-model nai_2x2_template `
  --start 10 --stop 20 --step 5 `
  --reference-point aluminum_shell_front `
  --source-energy 0.662 --source-radius 0.15 --nps 1e7
```

## MCNP5_RSICC 1.14 诊断与修复

```powershell
# 诊断（检查 80 列/tab/continuation/comment card/引用错误）
python -m mcnp_research_skill.cli diagnose-deck --input A.txt --mcnp-version mcnp5_rsicc_1_14

# 安全修复（tab→空格，超长注释→continuation，Unicode→ASCII）
python -m mcnp_research_skill.cli repair-deck --input A.txt --output fixed.txt
```

- 只修安全格式问题
- **不修改** 几何布尔表达式、F card、material、source physics

## 运行失败分析

```powershell
python -m mcnp_research_skill.cli analyze-run-failure `
  --output o.txt --stderr e.txt --context plan.json
```

- 默认分析 output **前 300 行**，不解析/展示完整日志
- 结合模型、源策略、tally、postprocess 意图给建议
- 识别 18 类错误（fatal/input_format/geometry/material/tally/source/mode/runtime）

## NPS vs Bq

- `--nps` 是 MCNP histories
- "源强度 1e7" → 解释为 NPS，带 `SOURCE_STRENGTH_INTERPRETED_AS_NPS` warning
- "活度 1e6 Bq" → `ACTIVITY_NORMALIZATION_UNSUPPORTED`，不映射为 NPS

## F8 与非 F8

| 能力 | F8 | F2/F4/F5/F6/FMESH |
|------|:--:|:--:|
| inspect / diagnose / prepare / run / sweep | ✓ | ✓ |
| CSV 提取 / 绘图 | ✓ | ✗ |

非 F8 + CSV/plot 返回 `CSV_REQUIRES_F8`。非 F8 + run-only 正常继续。

## 版本历史

| Tag | Commit | 内容 |
|-----|--------|------|
| `v0.3.0-final-user-flow` | `eb60b3b` | NL planner + execute-plan + runtime + failure analyzer + user output + 712 tests |
| `v0.2-snapshot-670-tests` | `881ef51` | NL planner + diagnostics + repair + 3 models + reference points + 670 tests |

## 分支

| 分支 | 用途 |
|------|------|
| `main` | 当前最新稳定代码（= v0.3.0） |
| `feature/profiles-init` | 开发分支 |
| `legacy-v0.1` | 旧 main 备份 |
| `codex/v0.2-research-tooling` | v0.2 历史分支 |

## 验证

```powershell
python -m pytest -q                    # 712 passed
python -m mcnp_research_skill.cli --help
```

## 限制

- 不真实运行 MCNP/MPI 测试
- 不提供 MCNP 下载、破解或授权绕过
- 不支持 activity-to-count-rate 归一化（Bq → NPS）
- F2/F4/F5/F6/FMESH 后处理未实现
- NL planner 是 deterministic rule-based parser，不是 LLM
- 不改 legacy GUI / Origin / SPE / input generator
