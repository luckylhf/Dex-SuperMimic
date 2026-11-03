# 来源与许可

| 部分 | 来源 / 许可 | 处理方式 |
|---|---|---|
| `src/instanttrack` 与基线训练计算 | [InstantTrack](https://github.com/Huy-Quang-Dao/instantTrack)，MIT，Copyright 2026 Huy-Quang-Dao | 保留包名、原 LICENSE 和源码指纹；Dex 适配另行修改 |
| 仿真框架 | [mjlab](https://github.com/mujocolab/mjlab)，Apache-2.0 | 固定 `8bb2bc9e187797689ec82c78c35019afd2fd0376`，依赖安装，不复制框架代码 |
| Dex 转换接口 | [Dex-Video2Robot](https://github.com/luckylhf/Dex-Video2Robot) | 外部依赖，遵循其代码及第三方子模块许可 |
| Dex XML / mesh / URDF | 上述项目机器人资产，OpenAtom Open Hardware License 1.0 | Git 中只留说明；参考许可副本位于 `LICENSES/` |
| BONES / LAFAN | 各数据集网站许可 | 不分发原始或转换数据 |

SuperMimic 是方法来源。本包不是其官方发布，也不声称与原论文设置完全相同。此前也参考过 SuperMimic-Reproduced，但这里实际交付的是 InstantTrack 派生主链。

源头的远端 InstantTrack 副本缺少 Git 元数据，因此不虚构 upstream commit；`docs/source_manifest.json` 记录提取时核心文件的 SHA-256。数据特征使用的 `motion.py` 和 `kinematics.py` 保持字节一致并在测试中核对。

本包新增主流程是对既有 Dex 适配、数据工程和评估代码的整理。运行产生的权重、数据、视频及机器人资产不自动受代码 MIT 许可授权。
