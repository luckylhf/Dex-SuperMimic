# Ubisoft La Forge Animation Dataset（LAFAN1）

官方来源：[Ubisoft La Forge Animation Dataset](https://github.com/ubisoft/ubisoft-laforge-animation-dataset)。遵守许可下载原始 BVH 及元数据。不要把全部 LAFAN1 当成舞蹈。

本包现在使用内置 **Dex v7 的 LAFAN1 分支**，入口为 `dex-sm data convert --dataset lafan1`，不经过 SOMA 映射或旧 GMR 转换脚本。该分支使用 LAFAN1 的人体局部轴与骨盆朝向校准，并从低速、低高度片段估计足底朝向。缺乏可信足部校准观测时明确失败，不静默猜测。

目录建议 `raw/`、`sources.jsonl`、`processed_v7/`、`release_v7/`，与 BONES-SEED 分开。LAFAN1 是独立可选数据，不属于 12341 主数据，也不会自动混入新的 BONES-SEED release。旧 LAFAN1 转换数据应从 BVH 重做，旧 A 级标签不作为 v7 准入依据。清单字段见 [数据协议](../README.md)。
