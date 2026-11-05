# 数据目录与 V8 转换协议

本包支持 **BONES-SEED: Skeletal Everyday Embodiment Dataset** 的 SOMA Uniform BVH，以及 **Ubisoft La Forge Animation Dataset（LAFAN1）** 的原始 BVH。官方来源和许可见 [BONES-SEED](bones_seed/README.md)、[LAFAN1](lafan1/README.md)。SOMA 是骨架表示。训练集、转换后的动作和外部评估动作均不随代码分发。

`bones_seed/` 为主体数据，`lafan1/` 独立管理，`evaluation/` 放外部开发评测；不会自动混合。源人体、Dex 关节轨迹、训练特征是三个不同阶段。

## 来源清单

`data convert` 接受 JSONL，每行示例：

```json
{"id":"bones_wave_001","dataset":"bones_seed","source":"raw/example.bvh","actor":"actor_01","sampling_group":"stationary_upper","anchor":false,"evaluation_only":false}
```

LAFAN1 将 `dataset` 改成 `lafan1`。可在命令行统一指定 `--dataset`；省略时按骨架识别，显式数据集与骨架冲突会在转换前报错。自动识别不是来源鉴定；BONES-SEED 仅支持 SOMA Uniform，不能把 Proportional 或任意同名骨架标为已校准。

`source` 相对 JSONL 目录；`id` 只能含字母数字、下划线和横线，并在清单中唯一。`actor` 依据元数据填写；`sampling_group` 为 `dance / locomotion / stationary_upper / dynamic`。不能把全部 LAFAN1 或 Gaming 视作舞蹈，也不能虚造演员身份。下载来源、许可、原始 SHA-256 与分类依据随本地清单归档。

## 转换和产物

安装 `.[convert]`；仓库已包含匹配的 `assets/dex_evt`，不再需要 `DEX_GMR_ROOT` 或 `DEX_MIMIC_ROOT`。命令见 [V8 说明](../docs/RETARGET_V8.md)。

```text
bones_seed/ 或 lafan1/
  sources.jsonl
  raw/
  processed_v8_constrained/
    catalog.json        # 本次清单与完成状态
    records/            # 来源、转换器/模型指纹、质量等级、失败原因
    motions/            # 50 Hz root + joints 训练 NPZ，WXYZ
    work/<id>/
      motion.pkl        # AITViewer 预览，XYZW、29 个关节名
      motion.npz        # 与预览 PKL 同布局，不能冒充训练 NPZ
      motion.json       # 校准、限位、接触、自碰撞和版本记录
      motion.diagnostics.npz
      motion.support.json # hybrid_cpu_v1 脚部精修路由/回退统计
      motion.pose_errors.npz # 逐帧姿态、接触与局部窗口误差
      motion.check.json # 导出后独立 FK 检查
    status.json
  release_v8_constrained/
    manifest.json
    shard_000.json
    features/index.json
    features/shard_000.pt
```

V8 将 BVH 先重采样到 50 Hz 再完整求解全身、足部接触和手臂时序；不靠末尾重采样已求解的关节轨迹，不复用旧版身体结果。预览→训练导出只转换字段布局和四元数分量顺序，位置/关节值保持逐元素相同。

A 表示运动学训练候选，B 表示需检查/修复，C 表示转换失败。筛选包括物理与人体腕部限位、关节速度、根速度、足部穿透/静态悬空、支撑约束失败、人体—机器人骨盆/躯干/手臂方向误差，以及手臂自碰撞。姿态阈值见 `src/dex_supermimic/data/quality_pose.json`，逐轴速度容差见 `quality_v8.py`，自碰撞距离与窗口见 `v8/config.json` 的 `self_collision`。V8 在求解中约束每个关节的相邻帧变化，并按相邻采样区间逐轴验收，超限余量为 0.0001 rad/s。每段速度统计见记录中的 `quality.step_velocity`，自碰撞证据见 `quality.self_collision`，几何诊断见 `motion.check.json`。A 要求自碰撞检测证据完整，且声明的双臂—躯干/骨盆/髋/头及双臂互碰几何对未发现未解决穿透；这不等于连续时间无碰撞、全机器人碰撞认证、控制器可跟踪或动态平衡。手腕限位导致的目标取舍也需要人工查看。V8 不伪造旧 GMR 的预热/IK 恢复字段。

## 重建、缓存和训练准入

对已有 PKL/NPZ，可运行 `dex-sm data check-speed FILE` 查看 V8 速度诊断。构建新的完整 V8 记录时，使用独立目录执行 `data convert`。缓存复用同时核对源文件、训练产物、转换实现/配置/校准资源、模型/网格和数值库版本。旧版或指纹变化明确拒绝复用；不覆盖原结果。默认 **1 个 CPU worker**，数值库单线程，`CUDA_VISIBLE_DEVICES` 为空；增加 `--workers` 会增加 CPU/内存占用。

有效缓存复用时，演员、分类、锚点、评测用途以当前清单为准并写回。清单不可伪造等级、产物路径、训练资格或转换版本等派生字段。`catalog.json` 记录本轮来源清单；构建拒绝未完成目录、过期元数据、旧转换器和被删掉的记录。A 级中若有 `evaluation_only=true`，构建明确拒绝。

`data build` 接受当前 V8 记录，校验转换身份与源模型、NPZ 哈希，并检查训练特征的边界帧 goal 一致性；允许构建机的数值库与转换机不同，转换时版本仍完整保留。构建保持整段，超出容量明确失败，不静默裁剪。失败记录保留，修复后使用新目录；不会删除源数据。

历史 release 的 `data import` 仍可校验并导入其既有 feature pack，以复现旧基线；这只验证归档一致性，不把旧数据认定为 V8 或动作质量合格。默认链接，独立搬迁加 `--copy-packs`。重新制作的训练集应走 V8 的 convert → build，不从旧 release 拼接。
