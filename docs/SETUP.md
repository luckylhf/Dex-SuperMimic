# 环境与安装

训练使用 Linux + NVIDIA CUDA；CPU 动作转换也支持 macOS。ROS Humble 使用独立的 Linux 环境。

机器人资产已随仓库提供。数据和权重的准备方式见[材料说明](DISTRIBUTION.md)。

| 组件 | 12341 实际环境 |
|---|---|
| 训练 Python | 3.11.15 |
| PyTorch | 2.10.0+cu128 |
| MuJoCo / mujoco-warp | 3.16.0 / 3.16.0 |
| warp-lang | 1.18.0+cu12 |
| NumPy | 1.26.4 |
| ONNX / ONNX Runtime | 1.21.0 / 1.31.0 |
| ROS | Humble，另用 Python 3.10 |
| GPU | RTX 5880 Ada 16Q，16 GiB |

## 训练和导出环境

建议独立 conda 环境，安装匹配驱动的 CUDA 版 PyTorch，然后安装本包。以下为基线版本入口；网络下载与驱动兼容需要在目标机器核对。

```bash
conda create -n dex_supermimic python=3.11 -y
conda activate dex_supermimic
python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install 'warp-lang==1.18.0+cu12' --extra-index-url https://pypi.nvidia.com
python -m pip install -e '.[train,video,test]'
python -m pip install --no-deps -r requirements-mjlab.txt
python -m pip install prettytable tqdm 'tyro>=1.0.1' trimesh scipy viser mjviser mediapy tensordict
export DEX_SUPERMIMIC_ROOT="$PWD"
dex-sm check
```

固定 mjlab 快照的声明要求 `torch>=2.14.0`，而基线实际运行于 `2.10.0+cu128`；因此显式以 `--no-deps` 安装该快照并单独安装所需依赖，避免解析器悄悄升级 PyTorch。这个组合属于已做运行验证的兼容组合，并非 mjlab 上游声明支持的依赖组合；`pip check` 可能报告这一已知冲突。在目标机器上完成环境检查和训练短测后再启动长训。历史验证记录见 [VALIDATION.md](VALIDATION.md)。

本项目保留 `instanttrack` 包名以维护来源和 checkpoint 兼容性。不要在同一环境再安装另一个 InstantTrack 实现。

## 转换环境

内置 Dex V8 支持 BONES-SEED 的 SOMA Uniform BVH 和 LAFAN1 原始 BVH。求解使用 CPU NumPy / SciPy / MuJoCo / OSQP / Mink，不需要 CUDA、PyTorch 或 mjlab；macOS 也可做转换。训练和特征构建的依赖按上节安装。

```bash
python -m pip install -e '.[convert]'
export DEX_SUPERMIMIC_ROOT="$PWD"
# 可省略：默认就是仓库根目录下 assets/dex_evt
export DEX_ASSETS="$PWD/assets/dex_evt"
dex-sm data convert --dataset bones_seed --manifest data/bones_seed/sources.jsonl --out data/bones_seed/processed_v8_constrained --workers 1
dex-sm data convert --dataset lafan1 --manifest data/lafan1/sources.jsonl --out data/lafan1/processed_v8_constrained --workers 1
```

仓库已包含 `model.json`、`mjcf/dex_29.xml`、对应网格及 `urdf/dex_29.urdf`，转换器校验模型哈希与关节顺序。SOMA 校准资源随包提供。首次转换 LAFAN1 前，按 [本地几何准备](../data/lafan1/README.md) 获取官方 FBX 和固定版本 ufbx 源码，执行 `dex-sm data prepare-lafan-geometry`。运行时使用 `data/lafan1/local_geometry/lafan1_surfaces.json`，或 `DEX_LAFAN_GEOMETRY` 指定的文件。外部机器人资产可用 `DEX_ASSETS` 指定。

V8 的独立复验、训练 NPZ 协议、缓存迁移与验证环境见 [转换说明](RETARGET_V8.md)。

## ROS 环境

ROS Humble 使用系统 Python 3.10，与训练的 Python 3.11 分开。安装本包基础依赖即可，不需安装训练 extra：

```bash
/usr/bin/python3.10 -m venv --system-site-packages .venv-ros
.venv-ros/bin/python -m pip install -e .
source /opt/ros/humble/setup.bash
source /path/to/dex_ros_workspace/install/setup.bash
export ROS_PYTHON="$PWD/.venv-ros/bin/python"
"$ROS_PYTHON" -c 'import rclpy; from bodyctrl_msgs.msg import MotorCtrl, MotorStatus, MotorStatusMsg, CmdMotorCtrl, Imu; from nav_msgs.msg import Odometry'
```

`bodyctrl_msgs` 从现有 Dex ROS 工作区构建；不从网上安装同名未知包。本包不包含 CAN / EtherCAT 驱动。消息语义及联调命令见 [部署](DEPLOYMENT.md)。

视频使用 FFmpeg 和中文字体，Linux 可安装 `ffmpeg fonts-noto-cjk`。非默认字体路径设置 `DEX_VIDEO_FONT`，无显示器时使用 `MUJOCO_GL=egl`。
