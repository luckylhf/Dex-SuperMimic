# 发布范围与本地材料

公开范围为主流程源码、配置、测试、文档、许可证、三个演示 GIF 及 `assets/dex_evt/` 机器人资产。参考动作、原视频、完整基线 ZIP 和 SHA-256 校验文件按本地材料管理。

运行前按下表准备权重和动作。

## 运行前需要准备的材料

| 材料 | 准备方式与用途 |
|---|---|
| `checkpoints/12341/ckpt_012341.pt`、`full_state_012341.pt` | 原始 12341 checkpoint 和完整训练状态，当前没有仓库下载附件；已有材料可按 [权重说明](../checkpoints/12341/README.md) 核对 |
| `checkpoints/12341/bundle/` | 回放所需 ONNX、MuJoCo 编译模型、控制契约和导出报告；须已有匹配导出结果，或从自己的 checkpoint 导出并验证 |
| `assets/dex_evt/` | 已随 Git 提供匹配的 XML、网格、URDF、元数据及原始 LICENSE，无需另行导入；外部目录可用 `DEX_ASSETS` 指定，说明见 [机器人资产说明](../assets/dex_evt/README.md) |
| `data/evaluation/` | 自行准备已授权的机器人动作与参考特征，用 `scripts/make_suite.py` 生成评估清单，见 [评估动作说明](../data/evaluation/README.md) |
| BONES / LAFAN 训练数据 | 按 [数据说明](../data/README.md) 获取、转换和构建；训练入口不附带这些数据 |
| LAFAN 人体表面 | 使用官方 FBX 在本地运行 `dex-sm data prepare-lafan-geometry`，步骤见 [LAFAN1 数据说明](../data/lafan1/README.md) |

也可按[训练入口](../README.md#数据到训练)训练自己的策略，再生成导出包和评测参考。

## 已有原始基线材料的校验

仅当本地同时具备 `checkpoints/12341/artifacts_manifest.json`、`data/evaluation/download_manifest.json`、清单列出的全部文件、控制契约和 `suite.json` 时，运行：

```bash
python scripts/check_baseline.py --sha256
```

检查器核对文件大小、SHA-256、12341 契约和三个参考动作。清单需与本地材料一同准备。材料齐备并通过校验后，再执行根 README 的 CPU 回放命令。使用自有策略和动作时，应按自己的材料生成导出包与评估清单。

## 本地归档

`scripts/package_delivery.py` 用于归档完整的本地基线。脚本先校验材料，再将源码和附件清单中的文件打包为 ZIP，并生成 SHA-256 校验文件。

打包脚本还需要本地 `data/evaluation/LOCAL_FILES.md`。生成物位于 `dist/`，用于具备对应材料使用权的本地基线工作区。三个已授权的演示 GIF 通过明确文件清单加入归档，原视频、BONES / LAFAN 训练集、虚拟环境和实验输出由归档排除规则覆盖。参考动作和权重的对外分发须按其各自授权处理。历史本地归档验证见 [验证记录](VALIDATION.md)。
