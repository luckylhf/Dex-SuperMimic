# 发布范围与本地材料

GitHub 当前发布主流程源码、配置、测试、文档、许可证、`assets/dex_evt/` 机器人资产和演示 GIF。完整基线 ZIP 及其 SHA-256 校验文件仅保留在维护者本地，已被 `.gitignore` 忽略，未上传到仓库或 Release。

`git clone` 和 GitHub 的 Download ZIP 均只包含 Git 跟踪的文件。下载源码会包含机器人资产，但不会取得 12341 权重或演示动作，仍不能直接运行文档中的完整基线回放与续训示例。

## 运行前需要准备的材料

| 材料 | 准备方式与用途 |
|---|---|
| `checkpoints/12341/ckpt_012341.pt`、`full_state_012341.pt` | 原始 12341 checkpoint 和完整训练状态，当前没有仓库下载附件；已有材料可按 [权重说明](../checkpoints/12341/README.md) 核对 |
| `checkpoints/12341/bundle/` | 回放所需 ONNX、MuJoCo 编译模型、控制契约和导出报告；须已有匹配导出结果，或从自己的 checkpoint 导出并验证 |
| `assets/dex_evt/` | 已随 Git 提供匹配的 XML、网格、URDF、元数据及原始 LICENSE，无需另行导入；外部目录可用 `DEX_ASSETS` 指定，说明见 [机器人资产说明](../assets/dex_evt/README.md) |
| `data/evaluation/` | 自行准备已授权的机器人动作与参考特征，用 `scripts/make_suite.py` 生成评估清单，见 [评估动作说明](../data/evaluation/README.md) |
| BONES / LAFAN 训练数据 | 按 [数据说明](../data/README.md) 获取、转换和构建；训练入口不附带这些数据 |

没有原始 12341 权重和参考动作时，可以按公开入口训练、导出和评估自己的策略，但不能声称复现了原始 12341 的权重或历史成绩。

## 已有原始基线材料的校验

仅当本地同时具备 `checkpoints/12341/artifacts_manifest.json`、`data/evaluation/download_manifest.json`、清单列出的全部文件、控制契约和 `suite.json` 时，运行：

```bash
python scripts/check_baseline.py --sha256
```

检查器核对文件大小、SHA-256、12341 契约和三个参考动作。上述清单也未随 Git 发布；源码克隆不能通过此项完整性检查。材料齐备并通过校验后，再执行根 README 的 CPU 回放命令。使用自有策略和动作时，应按自己的材料生成导出包与评估清单。

## 本地归档

`scripts/package_delivery.py` 保留给已具备完整原始基线材料的本地工作区使用。它会先校验材料，再打包源码和清单列出的文件，并生成 ZIP 与 SHA-256 校验文件；它不会下载缺失权重或数据，也不会上传 GitHub。

打包脚本还需要本地 `data/evaluation/LOCAL_FILES.md`。生成物位于 `dist/`，继续被 Git 忽略。原始视频、BONES / LAFAN 训练集、虚拟环境和实验输出不纳入该归档。历史本地归档验证见 [验证记录](VALIDATION.md)，该记录不代表存在公开下载附件。
