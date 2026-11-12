# Dex-SuperMimic

> 本项目保留 SuperMimic 路线的训练与评测基线，后续 Dex 全身跟踪开发见 [Dex-BlinkMimic](https://github.com/luckylhf/Dex-BlinkMimic)。当前版本为 `0.1.10`，历史算法基线为 `0.1.9`。

Dex-SuperMimic 让**一个策略**接受不同的参考动作，在 Dex 29 自由度机器人上执行全身跟踪。换参考不换权重：一支舞、一段新动作，只需替换参考特征即可直接跟踪，无需重新训练。

技术路线沿用 SuperMimic 的**学习动力学世界模型 + 可微展开 BPTT 策略优化**，基于 InstantTrack 的 mjlab / MuJoCo Warp 实现；重定向使用内置 Dex V8（逐轴限速拟合、固定骨架标定及分状态接触处理），回放接入既有 ROS 2 / MuJoCo 链路。

## 演示效果

GBTC、dance-boy、dance-girl 的参考动作来自视频转换。以下 GIF 展示各动作 15 秒的历史最佳与最新策略对比。

| GBTC | dance-boy | dance-girl |
| :---: | :---: | :---: |
| ![GBTC best vs latest](docs/gbtc_best_vs_latest.gif) | ![dance-boy best vs latest](docs/dance_boy_best_vs_latest.gif) | ![dance-girl best vs latest](docs/dance_girl_best_vs_latest.gif) |

## 仓库内容

本仓库以 **12341 EMA 策略及其控制契约**为整理基准，提供主流程源码、配置、测试、文档、演示 GIF 及 `assets/dex_evt/` 机器人资产。权重、编译模型和参考动作在本地准备，BONES-SEED / LAFAN1 训练数据按[数据说明](data/README.md)获取。

材料准备见[发布范围与本地材料](docs/DISTRIBUTION.md)，安装步骤见[环境说明](docs/SETUP.md)。

```text
BONES-SEED（SOMA Uniform BVH） / LAFAN1（原始 BVH）
    ↓ 内置 Dex V8，骨架校准、足部 XYZ 接触、手掌/肘轴与腕部限位
Dex robot PKL（预览）+ 50 Hz robot NPZ（训练）→ 质量分级 → 有界特征分片
    ↓ 世界模型 + BPTT，参考动作轮换，保留难度记忆
EMA checkpoint → ONNX + 机器人契约 / 编译模型
    ↓ 更换参考特征，无需为每支舞重新训练
原生 MuJoCo / ROS 2 + MuJoCo → 指标与参考 / 历史最佳 / 最新视频
```

## 基线回放

先按[权重说明](checkpoints/12341/README.md)和[动作说明](data/evaluation/README.md)准备匹配的 12341 权重、导出包与参考动作。机器人资产默认使用随仓库提供的 `assets/dex_evt/`。

在仓库根目录安装 CPU 回放依赖。基线校验需要 `artifacts_manifest.json`、`download_manifest.json` 及其列出的全部文件：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
export DEX_SUPERMIMIC_ROOT="$PWD"
python scripts/check_baseline.py --sha256
mkdir -p runs/baseline
DEX_EVALUATION_PROFILE=height_diagnostic_v1 dex-sm play --bundle checkpoints/12341/bundle --reference data/evaluation/references/dance_boy.npz --out runs/baseline/dance_boy.json
```

回放执行 CPU MuJoCo 闭环仿真，输出指标 JSON 和轨迹 NPZ。替换 `--reference` 可切换动作；GBTC 使用 `gbtc.npz`，dance-girl 使用 `dance_girl_original_start.npz`。ROS 回放和视频生成见[部署与评估](docs/DEPLOYMENT.md)。

使用自己的策略和动作时，安装[训练/导出环境](docs/SETUP.md)，分别生成参考文件和策略包：

```bash
dex-sm bundle motion --source /path/to/robot_motion.npz --out runs/my_motion.reference.npz
dex-sm bundle export --checkpoint /path/to/checkpoint.pt --out runs/my_bundle
```

输入为匹配 Dex 模型的机器人 NPZ；支持的人体 BVH 先经过内置 V8 转换，视频还需要独立的人体姿态提取。文件准备范围见 [发布范围与本地材料](docs/DISTRIBUTION.md)。

## 数据到训练

内置 **Dex V8** 支持以下数据集：

| 数据集 | 输入 | `--dataset` |
|---|---|---|
| [BONES-SEED: Skeletal Everyday Embodiment Dataset](https://huggingface.co/datasets/bones-studio/seed) | SOMA Uniform BVH | `bones_seed` |
| [Ubisoft La Forge Animation Dataset（LAFAN1）](https://github.com/ubisoft/ubisoft-laforge-animation-dataset) | 官方原始 BVH | `lafan1` |

SOMA 是人体骨架表示。内置 V8 将原始 BVH 求解为 50 Hz Dex 机器人动作，处理骨架标定、脚部与身体接触、腕部限位、逐轴速度和手臂避碰。当前使用 `V8_cpu_coupled_arms_20261105`；脚部支撑误差及穿地容差为 1 mm。方法与验收标准见 [V8 文档](docs/RETARGET_V8.md)。

先按[数据说明](data/README.md)准备 BVH 和来源清单。首次转换 LAFAN1 还需完成[本地几何准备](data/lafan1/README.md)。BONES-SEED 与 LAFAN1 分别转换、建库；外部评测动作单独管理。

```bash
# 仓库已包含 assets/dex_evt；安装内置 CPU 转换器
python -m pip install -e ".[convert]"
export DEX_SUPERMIMIC_ROOT="$PWD"
dex-sm data convert --dataset bones_seed --manifest data/bones_seed/sources.jsonl --out data/bones_seed/processed_v8_constrained --workers 1
# LAFAN1 单独转换、单独建库，不自动混入 BONES-SEED
dex-sm data convert --dataset lafan1 --manifest data/lafan1/sources.jsonl --out data/lafan1/processed_v8_constrained --workers 1
# 训练环境；默认 CPU 构建特征，不与训练争抢 GPU
dex-sm data build --records data/bones_seed/processed_v8_constrained/records --out data/bones_seed/release_v8_constrained
# 从头训练基础跟踪器
dex-sm train --config configs/train_fresh.json --data-release data/bones_seed/release_v8_constrained --log_dir runs/base
# 显式增加根位置反馈；取已训练基础策略初始化，重建优化器和 critic
dex-sm train --config configs/train_feedback.json --data-release data/bones_seed/release_v8_constrained --warm_start runs/base/ckpt_NNNNNN.pt --log_dir runs/feedback
```

`NNNNNN` 替换成实际 checkpoint 编号。默认优先 8192 环境；显存不足时再降低环境数或批量。分片容量 60 万帧、150 秒轮换、CPU 预取、固定 GPU 张量存储、每次切换清空 replay 并预热 64 步。训练实时记录资源、分片切换、动作覆盖率和 loss。

12341 由已有基础策略追加根位置反馈训练得到。原基线配置、完整状态恢复和学习率调度见[基线说明](docs/BASELINE.md)。

## 每半小时评估

训练会在初始状态、约每 30 分钟、最终状态保存评估任务。另开 CPU worker 消费队列，实际评估可能因视频渲染排队而延后；任务对应的 checkpoint 会保留。

以下示例要求本地已准备三个参考 NPZ；使用自有动作时，替换 `--reference` 名称与路径。

```bash
python scripts/make_suite.py --reference gbtc=data/evaluation/references/gbtc.npz --reference dance_boy=data/evaluation/references/dance_boy.npz --reference dance_girl=data/evaluation/references/dance_girl_original_start.npz --out data/evaluation/suite.json
dex-sm watch --queue runs/feedback/evaluation_queue --suite data/evaluation/suite.json --history runs/feedback/history --ros-python "$ROS_PYTHON" --ros-setup /opt/ros/humble/setup.bash --domain 226 --render
```

不传 `--ros-python` 时只验证原生 MuJoCo，视频会注明。ROS 评估使用相同 ONNX、参考、PD、初态，并要求两条物理轨迹逐元素一致。每个动作只显示参考、历史最佳、最新；后两者策略相同会标明。评估口径与 ROS 环境见 [部署与评估](docs/DEPLOYMENT.md)。

## 当前能力与限制

历史 12341 仿真记录：GBTC **18.92 秒**、dance-boy **80.20 秒**完成；dance-girl 原始起始动作 **165.58 / 241.56 秒**后终止。三个动作在原生 MuJoCo 与 ROS 回放中轨迹一致。这些是基线历史结果；本次整理的验证记录单列在 [验证报告](docs/VALIDATION.md)。

外部演示使用 `height_diagnostic_v1`：25 cm 高度偏差记录但不单独终止，倾斜超差仍终止。播完不等于精度合格。训练仍使用原终止规则。根位置纠偏使用**仿真真值**；真机还需状态估计、延迟、保护和硬件验证。现有 ROS 为 50 Hz 锁步联调，不是硬实时验收。

## 来源

- [InstantTrack](https://github.com/Huy-Quang-Dao/instantTrack)：核心网络、世界模型、BPTT 与 GPU 环境，MIT；保留 `instanttrack` 命名空间及许可证。
- [mjlab](https://github.com/mujocolab/mjlab)：仿真基础设施，安装固定提交。
- [Dex-Video2Robot](https://github.com/luckylhf/Dex-Video2Robot)：历史转换链及机器人资产来源。
- [NVIDIA SOMA Retargeter](https://github.com/NVIDIA/soma-retargeter) 与 [GMR](https://github.com/YanjieZe/GMR)：人体校准、接触处理及 LAFAN1→G1 坐标参考；本仓库转换器是面向 Dex 的本地实现，不是官方 Dex 转换器。
- [BONES-SEED](https://huggingface.co/datasets/bones-studio/seed) 与 [LAFAN1](https://github.com/ubisoft/ubisoft-laforge-animation-dataset)：人体动作来源，使用者须遵守各自许可。

详细来源与许可边界见 [THIRD_PARTY.md](THIRD_PARTY.md)。

Training data includes Motion Data by Bones Studio. Use of the underlying dataset is subject to the BONES Motion Capture Dataset License Agreement. [Bones Studio](https://bones.studio/) · [BONES-SEED license](https://bones.studio/info/seed-license)
