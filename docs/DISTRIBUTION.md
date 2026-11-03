# 完整交付与发布附件

完整包名称：`Dex-SuperMimic-12341.zip`。本地放在项目的 `dist/` 目录，旁边提供 `.sha256` 校验文件。解压后的顶层目录为 `Dex-SuperMimic/`。

包含：

- 主流程源码、配置、脚本、说明和许可证。
- `checkpoints/12341/ckpt_012341.pt`、`full_state_012341.pt`。
- `checkpoints/12341/bundle/`：已验证的 ONNX、MuJoCo 3.16.0 编译模型、控制契约、导出报告。
- `assets/dex_evt/`：完整机器人资产，保留 OpenAtom 原始许可。
- `data/evaluation/`：GBTC、dance-boy、dance-girl 的机器人动作、参考特征、评估清单和来源校验。

不包含 `data/evaluation/videos/` 中有版权的原视频、BONES / LAFAN 训练集、虚拟环境、实验输出或旧的实验编排。原视频仅供本地使用，不纳入附件完整性清单；已有 NPZ 参考的评估照常运行。BONES / LAFAN 按各自许可和 README 获取。

Git 跟踪源码，大文件由完整包提供；`.gitignore` 排除大文件是发布形式，不意味着交付时省略文件。发布 GitHub 时必须将完整 ZIP 和 SHA-256 同时上传到 Release，并在发布页关联；只有源码 ZIP / git clone 的用户仍需取得这个附件。本次已生成本地文件，没有自动上传 GitHub，也没有宣称存在尚未发布的下载地址。

解压后，在 Linux 的回放环境运行：

```bash
python scripts/check_baseline.py --sha256
```

检查器核对两个附件清单中的实际文件、大小与 SHA，并确认 12341 契约和三个参考动作均存在。再执行根 README 的 CPU 回放命令。

打包命令：

```bash
python scripts/package_delivery.py
```

该命令先核对附件，再打包源码和清单指定的文件；不会将 `runs/`、BONES、LAFAN、个人环境或 Git 历史混进去。
