# LAFAN1（可选，不属于 12341 主数据）

官方来源：[Ubisoft La Forge Animation Dataset](https://github.com/ubisoft/ubisoft-laforge-animation-dataset)。按其许可和说明下载原始 BVH 及元数据。不要把全部 LAFAN1 视为舞蹈数据。

目录建议 `raw/`、`processed/records/`、`processed/motions/`，与 BONES 分开。LAFAN 骨架需使用 Dex-GMR 对应的 LAFAN 映射，不能调用本包 SOMA Uniform 转换入口。完成匹配模型的机器人 NPZ 和质量记录后，才可按数据协议显式纳入新的训练 release；本仓库默认不混入。
