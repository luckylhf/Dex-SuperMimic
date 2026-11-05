# BONES-SEED: Skeletal Everyday Embodiment Dataset

官方来源：[bones-studio/seed](https://huggingface.co/datasets/bones-studio/seed)。使用自己的账号接受数据条款，下载 **SOMA Uniform BVH** 及配套元数据。SOMA 是骨架表示，不是数据集名称；Proportional 不与 Uniform 混用校准。

本包使用内置 **Dex V8** 从人体 BVH 完整求解到 Dex，入口为 `dex-sm data convert --dataset bones_seed`。数据站的 G1 CSV 已是另一机器人的关节轨迹，不能直接作为 Dex 数据或代替人体输入。无需外部 Dex-GMR / Dex-Mimic 转换环境。

将 BVH 放到 `raw/`，依据元数据制作 `sources.jsonl`，字段和产物见 [数据协议](../README.md)。下载保留原始路径、大小、SHA-256 和许可版本；新版输出使用 `processed_v8_constrained/`、`release_v8_constrained/`，不会覆盖旧结果。

历史 12341 基线曾记录 52,063 条转换候选、41,043 条 A 级候选、30 个特征分片。这是旧转换链的归档统计，不代表 V8 重新转换后的数量或质量验收；需从原始 BVH 重新转换和筛选。演员、类别、镜像关系随数据元数据管理，不随代码发布。
