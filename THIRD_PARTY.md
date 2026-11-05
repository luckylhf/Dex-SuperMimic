# 来源与许可

| 部分 | 来源 / 许可 | 处理方式 |
|---|---|---|
| `src/instanttrack` 与基线训练计算 | [InstantTrack](https://github.com/Huy-Quang-Dao/instantTrack)，MIT，Copyright 2026 Huy-Quang-Dao | 保留包名、原 LICENSE 和源码指纹；Dex 适配另行修改 |
| 仿真框架 | [mjlab](https://github.com/mujocolab/mjlab)，Apache-2.0 | 固定 `8bb2bc9e187797689ec82c78c35019afd2fd0376`，依赖安装，不复制框架代码 |
| 内置 Dex V8 | 本项目的 Dex 求解实现；参考 [NVIDIA SOMA Retargeter](https://github.com/NVIDIA/soma-retargeter) v0.2.1 与 [GMR](https://github.com/YanjieZe/GMR) 的校准/接触方法 | NVIDIA 校准零姿态和足部配置以 Apache-2.0 随包，保留 `src/dex_supermimic/data/v8/reference/NVIDIA/LICENSE`；GMR 参考配置及 MIT 许可位于同一 `reference/` 下的 `GMR_*`，不是官方 Dex 发布 |
| 历史 Dex 转换链 | [Dex-Video2Robot](https://github.com/luckylhf/Dex-Video2Robot) | 旧基线来源；当前两个数据集的转换不再依赖其运行环境 |
| Dex XML / mesh / URDF | 上述项目机器人资产，OpenAtom Open Hardware License 1.0 | 随 Git 分发；原始许可保留在 `assets/dex_evt/LICENSE`，参考许可副本位于 `LICENSES/` |
| BONES-SEED / LAFAN1 | [BONES-SEED](https://huggingface.co/datasets/bones-studio/seed)、[LAFAN1](https://github.com/ubisoft/ubisoft-laforge-animation-dataset) 的各自许可 | 不分发数据集动作或转换产物；随包 SOMA 零姿态是 NVIDIA 仓库的校准资源 |

SuperMimic 是方法来源。本包不是其官方发布，也不声称与原论文设置完全相同。此前也参考过 SuperMimic-Reproduced，但这里实际交付的是 InstantTrack 派生主链。

源头的远端 InstantTrack 副本缺少 Git 元数据，因此不虚构 upstream commit；`docs/source_manifest.json` 记录提取时核心文件的 SHA-256。数据特征使用的 `motion.py` 和 `kinematics.py` 保持字节一致并在测试中核对。

本包新增主流程是对既有 Dex 适配、数据工程和评估代码的整理。运行产生的权重、数据、视频及机器人资产不自动受代码 MIT 许可授权。

腕部人体范围参考 [NASA OCHMO-STD-100.1A Rev A，第 82 页](https://www.nasa.gov/wp-content/uploads/2023/04/ochmo-std-100.1a.pdf#page=82)。软限位、轴映射和与机器人硬限位相交的策略由本项目定义，并非 NASA 提供的机器人转换算法。v7 原实现的文件指纹见 `src/dex_supermimic/data/v8/provenance.json`。


## 本地固定人体表面参考

LAFAN1参考来自Ubisoft官方 `fbx/model_skeleton.fbx`；SOMA参考来自NVIDIA官方 `soma_base_skel_minimal.usd`。本地骨骼表面配置记录原资产SHA及提取方式，原模型/数据的原始许可继续适用。原始 FBX/USD 及提取工具未随 Git 发布；冻结后的骨骼表面 JSON 随包提供。参考地址与原始资产哈希见 `src/dex_supermimic/data/v8/reference/SOURCE_GEOMETRY.md`。

## Mink 运行依赖

[Mink](https://github.com/kevinzakka/mink)，Apache-2.0，固定运行版本 1.4.0；通过依赖安装调用其 CollisionAvoidanceLimit，不复制第三方源码。局部轨迹恢复、碰撞对选择和验收策略属于本项目实现。qpsolvers 4.12.0 为 Mink 运行依赖。
