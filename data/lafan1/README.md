# Ubisoft La Forge Animation Dataset（LAFAN1）

官方来源：[Ubisoft La Forge Animation Dataset](https://github.com/ubisoft/ubisoft-laforge-animation-dataset)。遵守许可下载原始 BVH 及元数据。不要把全部 LAFAN1 当成舞蹈。

本包现在使用内置 **Dex V8 的 LAFAN1 分支**，入口为 `dex-sm data convert --dataset lafan1`，不经过 SOMA 映射或旧 GMR 转换脚本。该分支使用 LAFAN1 的人体局部轴与骨盆朝向校准，并依据 Ubisoft 官方参考人体鞋底表面建立固定鞋底法向、脚跟和前掌点；转换前校验 Toe 相对 Foot 的固定旋转、骨架层级和踝到趾尺寸，不从动作估计足底朝向。没有站立、全程腾空、摔倒或躺卧都不影响同一骨架标定。

目录建议 `raw/`、`sources.jsonl`、`processed_v8_constrained/`、`release_v8_constrained/`，与 BONES-SEED 分开。LAFAN1 是独立可选数据，不属于 12341 主数据，也不会自动混入新的 BONES-SEED release。旧 LAFAN1 转换数据应从 BVH 重做，旧 A 级标签不作为 V8 准入依据。清单字段见 [数据协议](../README.md)。
