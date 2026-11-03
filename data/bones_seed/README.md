# BONES-SEED

来源：[bones-studio/seed](https://huggingface.co/datasets/bones-studio/seed)。用自己的 Hugging Face 账号接受数据条款并获准访问，按数据卡下载 **SOMA Uniform BVH** 及配套元数据。仓库不提供账号、token、压缩包或绕过许可的方法。

本基线需要人体 SOMA Uniform，经 Dex-GMR 重新求解到 Dex；数据站的 G1 CSV 已是另一机器人的关节轨迹，不能直接当 Dex 数据，也不使用 SONIC 的策略轨迹替代人体原始数据。SOMA Proportional 与 Uniform 不混用映射。

将解压后的 BVH 放到 `raw/`，按元数据生成 `sources.jsonl`，字段见 [数据协议](../README.md)。下载应保存原始路径、大小、SHA-256 和许可版本；转换记录保存其派生关系。

基线档案：52,063 条转换候选、41,043 条 A 级训练候选、30 个特征分片；具体演员 / 类别 / 镜像来源属于下载数据的元数据，不随代码发布。重新筛选的集合可能不同，不应只按总数声称复现 12341。
