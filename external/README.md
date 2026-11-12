# 外部依赖

| 用途 | 项目与准备方式 |
|---|---|
| 训练仿真 | [mjlab](https://github.com/mujocolab/mjlab)，按根目录 `requirements-mjlab.txt` 安装固定提交 |
| ROS 消息 | 在 Dex ROS 工作区构建 `bodyctrl_msgs`，接口和环境准备见[部署说明](../docs/DEPLOYMENT.md) |
| 视频动作预处理 | [Dex-Video2Robot](https://github.com/luckylhf/Dex-Video2Robot)，在独立环境中按其文档处理视频 |

BONES-SEED / LAFAN1 的 BVH 转换使用本包内置 V8，安装步骤见[环境说明](../docs/SETUP.md)。各依赖的来源与许可见[第三方说明](../THIRD_PARTY.md)。
