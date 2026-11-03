# 环境与安装

训练目标平台为 Linux + NVIDIA CUDA；macOS 可阅读代码、准备文件，不承诺 GPU 训练或 ROS Humble 原生运行。

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

固定 mjlab 快照的声明要求 `torch>=2.14.0`，而基线实际运行于 `2.10.0+cu128`；因此显式以 `--no-deps` 安装该快照并单独安装所需依赖，避免解析器悄悄升级 PyTorch。这个组合属于已做运行验证的兼容组合，并非 mjlab 上游声明支持的依赖组合；`pip check` 可能报告这一已知冲突。训练环境从零重建尚须验证，不能把复用训练依赖的打包测试视为完整训练环境重建。纯 CPU 回放环境已另用全新虚拟环境和实际完整 ZIP 验证，见 `VALIDATION.md`。

本项目保留 `instanttrack` 包名以维护来源和 checkpoint 兼容性。不要在同一环境再安装另一个 InstantTrack 实现。

## 转换环境

按 [Dex-Video2Robot](https://github.com/luckylhf/Dex-Video2Robot) 的文档安装 GMR 转换依赖。经核对的工作树 HEAD 为 `6f848794a1bac6e656c3baa8f9fbcc62600fc781`；本次使用的转换脚本和骨架加载器没有未提交修改。克隆后应核对对应接口，避免使用同名旧版实现。

```bash
export DEX_GMR_ROOT=/path/to/Dex-Video2Robot/Dex-GMR
export DEX_MIMIC_ROOT=/path/to/Dex-Video2Robot/Dex-Mimic
export DEX_ASSETS=/path/to/this-repo/assets/dex_evt
export PYTHONPATH=/path/to/this-repo/src
python -m dex_supermimic.cli data convert --manifest /path/to/sources.jsonl --out /path/to/processed
```

所需接口：`load_soma_file`、`retarget_frames(..., ik_recovery='table-retry')`、`pkl_to_npz.convert_single`、`check_motion.validate_motion`。转换器必须能写出带关节名、模型 SHA、四元数约定与 IK 审计的文件。旧版 GMR 若缺这些接口，须升级到匹配版本；不能只给旧 PKL 补字段后视为完成重定向。

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
