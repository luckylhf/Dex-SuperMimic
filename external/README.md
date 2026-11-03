# 外部依赖

- [Dex-Video2Robot](https://github.com/luckylhf/Dex-Video2Robot)：按上游文档克隆安装，配置 `DEX_GMR_ROOT` / `DEX_MIMIC_ROOT`；本仓库不再嵌套复制其工程。
- [mjlab](https://github.com/mujocolab/mjlab)：通过根目录 `requirements-mjlab.txt` 固定提交安装。
- `bodyctrl_msgs`：从现有 Dex ROS 工作区构建安装。所需字段见 `docs/DEPLOYMENT.md`。

这些依赖需各自遵守原始许可。不要将个人 checkout、虚拟环境、编译缓存提交到本目录。
