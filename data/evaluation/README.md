# 外部评估动作

公开仓库在本目录仅提供本说明，不包含 GBTC、dance-boy、dance-girl 的机器人 NPZ、参考特征或 `suite.json`，也没有提供这些数据的 Release 附件。`download_manifest.json` 和 `LOCAL_FILES.md` 属于维护者本地归档，未随 Git 发布。仓库展示的 GIF 不能作为回放输入；`videos/` 中的原视频仅保留本地，已有 NPZ 参考的评估不依赖这些视频。

这里放自有 / 已授权的 GBTC、dance-boy、dance-girl 或其他新动作；它们没有本仓库可公开提供的统一下载地址。由视频先提取人体动作，再经现有 Dex-GMR / Dex-Mimic 得到匹配模型的机器人 NPZ。

推荐 `motions/` 放机器人 NPZ，`references/` 放 `dex-sm bundle motion` 生成的目标特征。`scripts/make_suite.py` 生成带 SHA 的冻结评估清单。

12341 比较使用 GBTC 947 帧 / 18.92 秒、dance-boy 4011 帧 / 80.20 秒、**dance-girl original-start** 12079 帧 / 241.56 秒。后者保留开头手部已有动作，不应替换成加站立过渡的 246.4 秒版本。

GBTC 原机器人源 SHA：`338cdbe0b58bc1ec853f443cec2180fffab57a2852e2ab1dbe5296ea429d7b7f`。

dance-boy 原机器人源 SHA：`505a9cdee9c42aebaf258ab510b17fd2cc6e4fff5ebd2daeaa4a7bbbc06c4a1f`。

完整长度必须从实际 reference 元数据核验，不能靠文件名猜版本。评估动作不进入训练来源清单。
