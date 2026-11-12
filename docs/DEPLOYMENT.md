# 部署与评估

以下命令以 12341 导出包和评测动作为例，运行前先按[材料说明](DISTRIBUTION.md)准备文件。使用自己的策略和动作时，替换对应路径。

## 输出与输入

导出目录包含 `policy.onnx`、`contract.json`、`model.mjb`、`export_check.json`。导出检查 64 组随机输入，PyTorch / ONNX 最大动作差须小于 1e-3。`model.mjb` 绑定 MuJoCo 版本；更换版本或平台应从 XML 重新编译并重新验证，不只拷贝二进制。

机器人 NPZ 经 `dex-sm bundle motion` 转成独立参考 NPZ，包含根状态、关节状态、FK 身体状态、未来目标和元数据。同一个策略可以接受任意匹配模型、关节序和特征约定的参考，不需重新导出策略。

`DEX_ASSETS` 覆盖机器人目录，`DEX_SUPERMIMIC_ROOT` 覆盖工作根目录；默认根为当前工作目录。所有命令推荐在仓库根执行。

## ROS 仿真

```bash
source /opt/ros/humble/setup.bash
source /path/to/dex_ros_workspace/install/setup.bash
export DEX_EVALUATION_PROFILE=height_diagnostic_v1
"$ROS_PYTHON" -m dex_supermimic.cli ros --bundle checkpoints/12341/bundle --reference data/evaluation/references/dance_boy.npz --out runs/baseline/dance_boy_ros.json --ros-domain 226
```

ROS 节点在 localhost、独立 domain 215–232 和 `/supermimic_demo` 命名空间工作。选择当前无人使用的 domain；单个 worker 串行评估，不同 worker 不得复用 domain。启动器只清理自己创建的两个子进程，并写 cleanup 记录。

所需外部消息接口：

| 消息 | 使用字段 |
|---|---|
| `MotorCtrl` | `name` 电机 ID；`pos/spd/tor/kp/kd` |
| `CmdMotorCtrl` | `header`、`cmds[]` |
| `MotorStatus` | `name/pos/speed/current` |
| `MotorStatusMsg` | `header`、`status[]` |
| `Imu` | `header`、`orientation`、`angular_velocity` |
| `nav_msgs/Odometry` | `header`、`pose.pose.position`（仿真根位置） |

电机 ID 与顺序固定于 `ros_demo.py`，启动时对照契约关节名检查。会话 ID 与帧号拒绝旧帧；每步等完整 29 关节新命令后推进仿真。该锁步协议验证接口与计算一致性，不证明异步真机的延迟、频率或安全。

## 完整评测和视频

```bash
dex-sm evaluate --checkpoint checkpoints/12341/ckpt_012341.pt --suite data/evaluation/suite.json --out runs/evaluation_12341 --history runs/history --ros-python "$ROS_PYTHON" --ros-setup /opt/ros/humble/setup.bash --domain 226 --render
```

输出每段的原生 / ROS 指标、记录轨迹、两者逐元素一致性检查、汇总、历史最佳和 `comparison.json`。视频按记录的闭环轨迹渲染，终止后冻结画面并标注原因。视频：参考 / 历史最佳 / 最新；相同策略 SHA 标明相同；镜头各自跟随根位置，并提供同尺度世界 XY 轨迹显示漂移。

历史最佳先比较是否完成；都未完成时，时长差大于 0.1 秒优先更长；否则按平均身体误差、最大根误差排序。不同参考 SHA、评测 profile、截断长度、模型或 ROS/native 模式不可混入同一 history。

history 身份还包含实际编译模型 SHA 和完整控制契约（关节顺序、PD、action scale、观测/反馈、控制频率、物理步长、终止阈值、MuJoCo 版本等）。仅 checkpoint 路径/哈希、策略哈希和迭代号属于待比较模型身份，允许变化。回放前校验一次，更新最佳记录前在锁内再次校验；同源 XML 但编译模型或控制参数不同也会被拒绝。

旧版 history 的身份信息不足，不能静默沿用。请新建 history 目录并先重评 12341，再比较后续模型；旧报告和视频无需删除。

首次使用 history 没有既往最佳，首个结果就是历史最佳。若要与 12341 比，先将 12341 在同一 suite 下评估一次，再评估新模型。不要把不同舞蹈起始版本的最佳记录直接拼接。

也可加入较难的 BONES 长舞蹈，在生成 suite 时用 `--in-training case_name` 明确标记为训练内探针；汇总保留 `training_member`。`external` 是兼容历史报告的结果容器键名，是否训练内以这个字段为准，不能仅凭容器名声称独立测试。

`--max-steps` 用于工程短测；默认 0 为整段。无 ROS 时视频明确标记原生 MuJoCo。零更新状态仍有参考前馈，不能将其视为完全静止或无控制器。

外部 `height_diagnostic_v1` 只屏蔽高度偏差单项终止；保留并报告高度、倾斜、关节和全身误差。`strict_v1` 同时保留 25 cm 高度及倾斜阈值。所有曲线和视频记录其 profile，禁止混用结论。

## 真机衔接边界

当前提供 ROS 仿真适配和可核对的关节 / PD / ONNX 契约。根位置来自仿真，真机须提供经验证的估计源，并验证初态、时延、量化、频率、执行器与保护逻辑。仓库没有一键发送真机电机命令的入口。
