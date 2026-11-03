# 环境与安装

训练目标平台为 Linux + NVIDIA CUDA；macOS 可阅读代码、准备文件，不承诺 GPU 训练或 ROS Humble 原生运行。

以下命令安装代码和依赖，不会下载权重、机器人资产或动作数据。当前没有完整基线 Release 附件，运行前需按 [发布范围与本地材料](DISTRIBUTION.md) 准备输入文件。

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

固定 mjlab 快照的声明要求 `torch>=2.14.0`，而基线实际运行于 `2.10.0+cu128`；因此显式以 `--no-deps` 安装该快照并单独安装所需依赖，避免解析器悄悄升级 PyTorch。这个组合属于已做运行验证的兼容组合，并非 mjlab 上游声明支持的依赖组合；`pip check` 可能报告这一已知冲突。训练环境从零重建尚须验证，不能把复用训练依赖的打包测试视为完整训练环境重建。纯 CPU 回放曾使用全新虚拟环境和维护者本地完整归档验证；该归档未公开上传，历史记录见 `VALIDATION.md`。

本项目保留 `instanttrack` 包名以维护来源和 checkpoint 兼容性。不要在同一环境再安装另一个 InstantTrack 实现。

## 转换环境

内置 Dex v7 支持 BONES-SEED 的 SOMA Uniform BVH 和 LAFAN1 原始 BVH。求解使用 CPU NumPy / SciPy / MuJoCo，不需要 CUDA、PyTorch 或 mjlab；macOS 也可做转换。训练/特征构建的依赖仍按上节安装。为保留历史回放契约，基础环境的版本固定项不因 v7 接入而修改。

```bash
python -m pip install -e '.[convert]'
export DEX_SUPERMIMIC_ROOT="$PWD"
# 可省略：默认就是仓库根目录下 assets/dex_evt
export DEX_ASSETS="$PWD/assets/dex_evt"
dex-sm data convert --dataset bones_seed --manifest data/bones_seed/sources.jsonl --out data/bones_seed/processed_v7 --workers 1
dex-sm data convert --dataset lafan1 --manifest data/lafan1/sources.jsonl --out data/lafan1/processed_v7 --workers 1
```

必须准备 `model.json`、`mjcf/dex_29.xml`、对应网格及 `urdf/dex_29.urdf`；转换器校验模型哈希与关节顺序。人体校准资源随本包打包，不依赖维护者机器上的校准路径；机器人资产仍需单独准备。无需设置历史 `DEX_GMR_ROOT`、`DEX_MIMIC_ROOT`，也不从外部同名脚本导入转换函数。

v7 的独立预览、训练 NPZ 协议、缓存迁移与验证环境见 [转换说明](RETARGET_V7.md)。安装不会自动下载数据或机器人资产，不会启动训练。

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
