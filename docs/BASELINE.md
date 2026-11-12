# 12341 基线

本文记录 12341 的配置和历史结果。回放及续训前，先按[材料说明](DISTRIBUTION.md)准备匹配的权重和数据。

基线采用 EMA actor，即 checkpoint 中的 `pi`。`pi_live` 是在线更新权重，不能在评估时与 EMA 混用。

完整接口保存在 [baseline_12341.json](../configs/baseline_12341.json)。关键约定：29 个具名关节；参考 50 Hz；物理步长 5 ms、4 次子步；10 帧历史；102 维观测；10 帧未来参考组成 730 维目标。电机反馈先转 float32，再减默认关节角，避免 ROS 与原生计算的舍入分叉。

动作目标为 `q0 + 0.25 * clip(action, -20, 20)`；策略包含参考关节前馈及根误差纠偏。根误差在 heading 局部坐标中表示，截断为 ±3 m。不要混用其他工程中六轴零残差或不同 action scale 的契约。

## 数据与训练配方

Training data includes Motion Data by Bones Studio. Use of the underlying dataset is subject to the BONES Motion Capture Dataset License Agreement. [Bones Studio](https://bones.studio/) · [BONES-SEED license](https://bones.studio/info/seed-license)

原全量准备候选 52,063 条，最终 A 级 41,043 条，B 级 5,262 条，C 级 5,758 条。A 级总计 14,155,221 帧，约 78.6 小时；A 表示运动学筛选合格候选，不代表每条动作已被控制器完整跟踪。

全部 A 级参与训练。30 个有界分片，每片容量 600,000 帧，285 条锚点复用在各片中；因此分片帧数总和包含重复锚点，不等于独立数据时长。分类质量分配为舞蹈 40%、移动 25%、原地上身 25%、动态 10%；每类锚点 25%、新增 75%，类内先均衡演员再均衡片段。缺失分类时重新归一化。新数据构建器允许无锚点，不强制凑成 285 条。

`train_baseline.json` 保留 12341 所属反馈阶段的主要超参数：8192 环境、512 replay steps、horizon 16、WM window 8、batch 4096、5 次 WM 更新、UTD 0.4、EMA 0.995、bf16、融合 Adam、编译、参考前馈和根反馈。分片 150 秒轮换，保留按来源 ID / 相对秒记录的难度统计，切换时清空旧 replay 索引并预热。

原 12341 先继承已训练的基础 actor / WM，再训练根反馈，随后完整状态恢复续训。公开入口的 `train_fresh.json` 是从随机初始化开始的基础配方，`train_feedback.json` 是追加根反馈的配方；重新训练的结果会随随机种子和调度变化。

## 恢复与停止

```bash
dex-sm data import --source /path/to/verified-release --out data/bones_seed/release
dex-sm train --config configs/train_baseline.json --data-release data/bones_seed/release --resume checkpoints/12341/full_state_012341.pt --log_dir runs/resume --max_hours 6 --stop-file runs/STOP
```

`--max_hours` 是**含 checkpoint 已用时间的累计预算**，不是新增小时数。新建 log 目录；已有目录拒绝覆盖。`--resume` 需要完整状态且冻结数据 manifest SHA 一致；恢复 actor、WM、critic、优化器、EMA、计数和难度记忆。Replay 不保存在 checkpoint，恢复后重新采集 64 步。`--warm_start` 是从不带根反馈的基础权重初始化反馈模型，重建 critic / 优化器，不等于 resume。

恢复后的策略学习率不会默认回到配方峰值：

- 新版完整 checkpoint 包含 `policy_lr_schedule`，保存曲线参数、已用调度时间和冻结结束迭代。恢复接续这条曲线，也不会重复开启冻结窗口；延长 `--max_hours` 只延长停止预算，原曲线走完后保持最低学习率。
- 12341 等旧 checkpoint 没有调度器状态。迁移时首轮严格使用已保存的优化器学习率（12341 约 `1.95996e-5`），根据旧配方峰值、最低比例和原预算剩余时间接续余弦尾段，原预算结束后保持末值。没有剩余预算时保持保存值；零学习率等无法无歧义迁移的旧状态会明确报错。
- 旧 checkpoint 缺少阶段起点，无法精确恢复其历史调度时间；上述迁移保证边界连续，不声称还原所有历史时刻。启动时的 `policy_lr_schedule.json` 记录采用的方式。
- 只有确实要开启一条新曲线时，才使用 `--reset_pi_schedule`；这会按当前 `--pi_lr`、剩余预算和 `--freeze_pi_iters` 重置调度。普通 resume 中这些参数不会覆盖已保存的策略曲线。WM / critic 仍按当前 `--wm_lr` 配置。



停止文件出现后，在当前更新结束时保存最终 checkpoint 并退出：

```bash
touch runs/STOP
```

正常退出会冲洗覆盖统计并关闭预取线程。硬杀进程不保证最后一次更新保存。

保留原基线语义：`freeze_pi_iters` 以学习率归零实现，仍会执行优化器 / EMA 步骤；不能把它描述成完整冻结所有内部状态。续训退化的后续探索未合入主基线。
