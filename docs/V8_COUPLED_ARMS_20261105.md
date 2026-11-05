# V8 默认联合手臂避碰合入 — 2026-11-05

版本：`dex-supermimic 0.1.9`；发布标识 `V8_cpu_coupled_arms_20261105`；
求解策略 `per_axis_velocity_v8_mink_arm_recovery_v2`；碰撞策略
`mink_arm_local_recovery_v2`。

## 默认行为

`data/v8/self_collision.py` 的 `refine()` 在每个已有碰撞窗口调用
`_window_sides()`，联合检查穿透碰撞对及整个窗口内低于配置安全间距的
碰撞对，自动选取相关手臂，再调用原 `_repair_window()`。

这修复了“另一侧手臂没有穿透，但距离不足 3.5 mm；QP 要求它让开，
却没有开放它的关节变量”产生的不可行约束。不是始终开放双臂，
没有碰撞的动作仍不触发修复。报告增加 `side_selection`，列出
`collision_sides`、`margin_added_sides` 和 `margin_pairs`。

原局部优化器、窗口、限位、逐轴速度、地面约束、3.5 mm 求解目标、支撑
接触保护和失败回滚保持不变。新增手臂若有支撑接触，仍拒绝局部修复。
新策略及源码指纹会使旧缓存失效，已有动作文件不会自动改写或改级。

## 验证

- 正式仓库 **111 项测试通过，无跳过**；Dex-Frax 同步副本 **67 项通过，无跳过**。
- 新增几何回归明确复现旧单臂求解 `primal infeasible`，并验证默认流程
  自动加入右臂后无碰撞；另验证新增右臂有支撑时继续拒绝修复。
- 原单臂案例仍只调整左臂；无碰撞动作逐值保持。
- 从 `/Users/loong/Desktop/test/00_nobody_原始人体.bvh` 重新运行正式
  `dex_supermimic.data.v8.convert` 默认入口，未调用独立重试脚本、未手动指定双臂。
- 完整输出 1,158 帧、50 Hz。第一窗口自动选左臂，片尾窗口自动由左臂扩展为双臂；
  两个窗口均修复成功。碰撞阶段原生帧由 **68 → 0**，旧版最终残留的 60 帧全部清除。
- 最终全片声明的 240 组碰撞对，每帧间隔 32 等分采样均无碰撞；最小距离
  约 2.7143 mm（位于前一个修复窗口的帧间采样）。这不是连续时间无碰撞证明。
- 与旧 V8 输出相比，根位置、根四元数、非手臂关节及片尾修复接缝前的
  第 0–1082 帧逐值不变。相邻关节速度违规为 0，当前全片运动学审核通过。
- 没有全库重新转换、训练、控制器或真机验证。历史 21 条碰撞阶段回归仍为历史证据。

验证产物：`../Dex-Frax/outputs/v8_default_merge_20261105/formal_default/`。
其中 `validation.json` 保存默认入口、窗口自动选择、密集检查和输出哈希。
备份：`../Dex-Frax/outputs/v8_default_merge_20261105/before_merge.tar.gz`。
发布回执：仓库根目录 `V8_FINAL_RELEASE.json`。

本次仅更新本地正式 V8 和 Dex-Frax 的 V8 副本，未同步远端、推送 Git，
也未修改 Dex-LAFAN-BONES 中另一份转换器。
