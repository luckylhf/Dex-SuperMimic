# Dex v7 数据集转换

## 数据集与版本

| 参数 | 数据集准确名称 | 输入 |
|---|---|---|
| `bones_seed` | [BONES-SEED: Skeletal Everyday Embodiment Dataset](https://huggingface.co/datasets/bones-studio/seed) | SOMA Uniform BVH |
| `lafan1` | [Ubisoft La Forge Animation Dataset（LAFAN1）](https://github.com/ubisoft/ubisoft-laforge-animation-dataset) | 官方原始 BVH |

SOMA 是骨架表示，不是第三个数据集。批处理入口会检查骨架与数据集标签是否一致；SOMA Proportional、任意改名骨架或 G1 CSV 不属于本接口支持范围。

代码位于 `src/dex_supermimic/data/v7/`，来自 2026-11-03 用户确认的独立 Dex v7。接入时保留求解数学、配置与腕部范围；改动是包内导入、相对校准资源、统一机器人路径和版本记录。导出后增加骨盆/躯干方向与静态悬空统计，作为筛选证据，不反向改变已求解动作。原实现文件哈希保存在 `provenance.json`。

独立 v7 的五段人工预览曾以 v6 身体为基础重新解算手臂；**本包的新数据集转换从原始 BVH 跑完整 v7 全身流程**，不读取旧 PKL 的腿部或根轨迹。

## 方法与保留的行为

1. 读取 BVH 的通道顺序、局部旋转、End Site 和单位，先将人体运动重采样至 50 Hz，旋转用 SLERP。使用各骨架的局部解剖轴恢复骨盆和躯干；LAFAN1 的骨盆向上轴用局部 +X，不能用倾斜的 Spine 平移向量代替。
2. BONES-SEED 使用 SOMA 的校准零姿态、脚跟/脚掌支点与足底法线。LAFAN1 用片段中低速、低高度的足部观测校准足底方向；没有可信观测就拒绝猜测。人体尺度、足部几何和手掌坐标一起转换到 Dex 模型。
3. 区分平脚、脚尖/脚跟支撑及离地，按接触段建立三维锚点并平滑过渡。通过骨盆和腿部联合调整满足足目标，按真实鞋网格限制穿地；XYZ 接触与脚掌朝向分别处理，脚尖支撑不会被强制铺平。
4. 保留上臂的屈肘轴与有符号弯曲角，沿整段寻找手臂解并做时序优化，减少 J3/J5 相互补偿造成的反肘方向。手掌的前向与横向共同约束姿态，避免只匹配手的位置。
5. J6/J7 使用人体活动范围的软惩罚与硬范围，再和机器人物理限位相交。人体范围来源是 [NASA OCHMO-STD-100.1A Rev A，第 82 页](https://www.nasa.gov/wp-content/uploads/2023/04/ochmo-std-100.1a.pdf#page=82)。

当前 Dex 模型中的腕部有效范围（关节坐标）：

| 关节 | 硬范围 | 软范围 |
|---|---|---|
| 左/右 J6 | −20° ～ +45° | −15° ～ +30° |
| 左 J7 | −76° ～ +76° | −70° ～ +65° |
| 右 J7 | −76° ～ +76° | −65° ～ +70° |

NASA 提供的是人体单轴范围，软范围、左右轴符号与物理限位相交是本项目的选择；不是完整的人体耦合活动空间或机器人硬件评级。URDF、MJCF 和控制器增益不因此改变。

接触处理参考 [NVIDIA SOMA Retargeter v0.2.1](https://github.com/NVIDIA/soma-retargeter/tree/cbdb2b494a2af82137bf9b6f15122d60167281c4) 的校准、接触分段、锚点过渡和骨盆/肢体联动；LAFAN1 人体轴参考 [GMR 的 G1 配置](https://github.com/YanjieZe/GMR)。Dex 的肘轴/手臂分支、腕部解剖约束和鞋网格处理由本项目实现。内置运行不调用官方 G1 转换器，也不宣称是官方 Dex 版本。

## 使用与接口

在仓库根目录准备机器人资产并安装：

```bash
python -m pip install -e '.[convert]'
export DEX_SUPERMIMIC_ROOT="$PWD"
# 非默认资产位置才设置 DEX_ASSETS
# export DEX_ASSETS=/absolute/path/to/dex_evt

dex-sm data convert --dataset bones_seed --manifest data/bones_seed/sources.jsonl --out data/bones_seed/processed_v7 --workers 1
dex-sm data convert --dataset lafan1 --manifest data/lafan1/sources.jsonl --out data/lafan1/processed_v7 --workers 1
```

清单格式见 [数据协议](../data/README.md)。默认一个 CPU worker，数值库单线程，并隐藏 CUDA 设备；增加 worker 会增加内存和 CPU 负载。转换不会连接远端、启动训练或替换既有数据。

经过检查再在训练环境中构建各自特征库，默认 CPU：

```bash
dex-sm data build --records data/bones_seed/processed_v7/records --out data/bones_seed/release_v7 --device cpu
dex-sm data build --records data/lafan1/processed_v7/records --out data/lafan1/release_v7 --device cpu
```

仅 A 级运动学候选进入新库，B 保留为待检查，C 保留失败原因；外部开发评测不得混入训练清单。这里不自动把两个 release 混成同一训练任务。

| 产物 | 协议及用途 |
|---|---|
| `work/<id>/motion.pkl` | `root_pos`、XYZW `root_rot`、`dof_pos`、29 个 `joint_names`；用配套 URDF 预览 |
| `work/<id>/motion.json` | 来源、模型、校准、配置、接触段、腕部限位和求解记录 |
| `work/<id>/motion.npz` | 预览 PKL 的同布局版本，不能当训练 NPZ |
| `work/<id>/motion.check.json` | 导出后 FK 检查、手臂方向、接触 XYZ、脚底高度与姿态误差 |
| `motions/<id>.npz` | 50 Hz、WXYZ、`root_joint_lossless_v1`、模型 SHA 与严格关节名顺序，供现有训练读取器 |
| `records/<id>.json` | 质量等级、来源/产物哈希、转换器指纹、数值库版本及清单元数据 |

训练导出只做字段布局和 XYZW→WXYZ 分量重排，不再次求解或插值。`instanttrack/motion.py`、`kinematics.py` 及现有训练/控制参数保持不变。历史 `retarget_soma.convert` 导入仍可用，内部改为 BONES-SEED v7、50 Hz；显式传入旧 `warm_frames` 会产生弃用提示，不再伪造 GMR 预热。

只做单段独立预览可运行：

```bash
python -m dex_supermimic.data.v7.convert /path/to/input.bvh /path/to/new_motion.pkl --source soma --fps 60
python -m dex_supermimic.data.v7.audit /path/to/new_motion.pkl
```

LAFAN1 用 `--source lafan`。低层独立入口可选原始帧率；数据集批处理固定 50 Hz。不要把不同帧率的同一帧编号直接当成相同时刻。

## 旧结果迁移

使用新的 `processed_v7` / `release_v7` 目录。旧 GMR 记录即使源文件哈希相同，也不允许冒用 v7 缓存或进入新 `data build`。当前缓存身份涵盖代码、配置、校准资源、机器人模型/网格与转换数值库；改变这些内容需要重新转换。构建特征时允许另一数值库版本，但仍验证原转换身份完整性及模型/实现是否匹配。

历史 release 导入仍用于复现旧基线，不是动作质量再认证。12341 权重、视频和历史统计保持归档身份，不能称为 v7 重训结果。此次集成不修改远端训练或旧数据。

## 本次验证与边界

2026-11-04，本地 macOS CPU，Python 3.11，NumPy 2.4.6 / SciPy 1.17.1 / MuJoCo 3.10.0：

- 44 项自动测试通过，包含原包 31 项和新增的网格变更识别、分流、旧缓存拒绝、训练四元数/顺序、方向筛选、腕部真实安装轴及校准资源检查。
- BONES-SEED 挥手前 180 个源帧、LAFAN1 `dance2_subject4` 前 60 个源帧分别通过批处理生成 75 / 99 个 50 Hz 帧；与独立 v7 对相同输入/帧率的结果比较，根位置、根朝向、全部 29 轴逐元素相同。
- 两段训练 NPZ 经现有训练读取函数检查，位置/关节值无损、四元数顺序正确。LAFAN1 99 帧通过现有 CPU FK、MotionLib 与有界缓存计算，goal 边界逐元素一致；验证脚本仅排除了 GPU 仿真配置的导入，不是完整 Linux `data build`/训练环境验收。
- LAFAN1 样例为 A 级；挥手样例为 B 级，右肩 pitch 在 9 帧超过模型速度限值（最大 12.27 rad/s，限值 7.22 rad/s）。保留 v7 动作及诊断，不为通过检查而放宽物理速度阈值。这也说明人工姿态认可与可直接训练的筛选是不同环节。
- 构建 wheel 并在独立解压目录导入，确认校准 BVH、配置和许可资源齐全，转换身份与源码运行一致。
- 本次只验证了上述样例和接口，未重新转换全量数据、未运行远端 GPU 训练。历史训练环境的 NumPy 1.26.4 / MuJoCo 3.16.0 固定项未修改；该环境的完整 v7 批量回归仍需后续验证。

运动学筛选不证明动态可跟踪性、平衡或自碰撞安全；足部接触为推断并假设平地。短片段不能代表全部数据集，腕部限位下的方向取舍仍可查看逐段报告和预览。
