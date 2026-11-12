# 来源与许可

| 部分 | 来源 / 许可 | 处理方式 |
|---|---|---|
| `src/instanttrack` 与基线训练计算 | [InstantTrack](https://github.com/Huy-Quang-Dao/instantTrack)，MIT，Copyright 2026 Huy-Quang-Dao | 保留包名、原 LICENSE 和源码指纹；Dex 适配另行修改 |
| 仿真框架 | [mjlab](https://github.com/mujocolab/mjlab)，Apache-2.0 | 固定 `8bb2bc9e187797689ec82c78c35019afd2fd0376`，依赖安装，不复制框架代码 |
| 内置 Dex V8 | 本项目的 Dex 求解实现；参考 [NVIDIA SOMA Retargeter](https://github.com/NVIDIA/soma-retargeter) v0.2.1 与 [GMR](https://github.com/YanjieZe/GMR) 的校准/接触方法 | NVIDIA 校准零姿态和足部配置以 Apache-2.0 随包，保留 `src/dex_supermimic/data/v8/reference/NVIDIA/LICENSE`；GMR 参考配置及 MIT 许可位于同一 `reference/` 下的 `GMR_*`，不是官方 Dex 发布 |
| 历史 Dex 转换链 | [Dex-Video2Robot](https://github.com/luckylhf/Dex-Video2Robot) | 旧基线来源；当前两个数据集的转换不再依赖其运行环境 |
| Dex XML / mesh / URDF | 上述项目机器人资产，OpenAtom Open Hardware License 1.0 | 随 Git 分发；原始许可保留在 `assets/dex_evt/LICENSE`，参考许可副本位于 `LICENSES/` |
| BONES-SEED / LAFAN1 | [BONES-SEED](https://huggingface.co/datasets/bones-studio/seed) 的专用协议、[LAFAN1](https://github.com/ubisoft/ubisoft-laforge-animation-dataset/blob/master/license.txt) 的 CC BY-NC-ND 4.0 | 原始动作、人体模型和 LAFAN 派生表面在用户本地准备；SOMA 零姿态来自 NVIDIA 校准资源 |
| LAFAN FBX 本地提取 | [ufbx](https://github.com/ufbx/ufbx)，MIT 或 Public Domain 许可 | 用户下载固定版本源码及其 LICENSE，提取命令临时编译调用 |
| GBTC、dance-boy、dance-girl 参考动作及演示 | 视频转换得到的历史开发评测材料 | 三个演示 GIF 随源码提供；原视频和回放参考在本地准备 |

SuperMimic 是方法来源。本包不是其官方发布，也不声称与原论文设置完全相同。此前也参考过 SuperMimic-Reproduced，但这里实际交付的是 InstantTrack 派生主链。

InstantTrack 核心文件的 SHA-256 记录在 `docs/source_manifest.json`。数据特征使用的 `motion.py` 和 `kinematics.py` 保持字节一致并在测试中核对。

本包新增主流程是对既有 Dex 适配、数据工程和评估代码的整理。运行产生的权重、数据、视频及机器人资产不自动受代码 MIT 许可授权。

腕部人体范围参考 [NASA OCHMO-STD-100.1A Rev A，第 82 页](https://www.nasa.gov/wp-content/uploads/2023/04/ochmo-std-100.1a.pdf#page=82)。软限位、轴映射和与机器人硬限位相交的策略由本项目定义，并非 NASA 提供的机器人转换算法。v7 原实现的文件指纹见 `src/dex_supermimic/data/v8/provenance.json`。


## 本地固定人体表面参考

LAFAN1 参考来自 Ubisoft 官方 `fbx/model_skeleton.fbx`，适用 CC BY-NC-ND 4.0。用户通过 `dex-sm data prepare-lafan-geometry` 在本地生成骨骼表面和鞋底标记。准备方法见 [LAFAN1 数据说明](data/lafan1/README.md)，使用和分发遵循 LAFAN1 许可。

SOMA 表面参考来自 NVIDIA 官方 `soma_base_skel_minimal.usd`，与校准零姿态、接触配置一起沿用 NVIDIA 许可说明。各参考资产的 SHA-256 和提取方法见 [来源记录](src/dex_supermimic/data/v8/reference/SOURCE_GEOMETRY.md)。

## BONES-SEED 成果署名

Training data includes Motion Data by Bones Studio. Use of the underlying dataset is subject to the BONES Motion Capture Dataset License Agreement. [Bones Studio](https://bones.studio/) · [BONES-SEED license](https://bones.studio/info/seed-license)

使用者须直接向发布方获取数据并接受对应许可，按自身机构或企业资格确定使用范围。成果发布须满足协议中的署名、数据可提取性和分发条件。

## Mink 运行依赖

[Mink](https://github.com/kevinzakka/mink)，Apache-2.0，固定运行版本 1.4.0；通过依赖安装调用其 CollisionAvoidanceLimit，不复制第三方源码。局部轨迹恢复、碰撞对选择和验收策略属于本项目实现。qpsolvers 4.12.0 为 Mink 运行依赖。

## 视频动作处理工具

视频动作处理建议使用 [GVHMR](https://github.com/zju3dv/GVHMR) 提取人体运动、[SMPL-X](https://smpl-x.is.tue.mpg.de/) 构建人体关节，并通过 Dex-GMR 重定向到 Dex 机器人。

- GVHMR：浙江大学 3D Vision Group，World-Grounded Human Motion Recovery via Gravity-View Coordinates（2024）。[软件许可](https://github.com/zju3dv/GVHMR/blob/main/LICENSE)限定教育、研究和非营利用途。
- SMPL-X：Max Planck Institute for Intelligent Systems 等，Expressive Body Capture（CVPR 2019）。模型和软件适用其[非商业许可](https://smpl-x.is.tue.mpg.de/modellicense.html)。
