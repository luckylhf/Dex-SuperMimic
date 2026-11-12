# Ubisoft La Forge Animation Dataset（LAFAN1）

官方来源为 Ubisoft La Forge Animation Dataset，数据及参考 FBX 适用 CC BY-NC-ND 4.0。原始动作、参考模型和本地派生文件均按该许可使用。公开分享改编材料须另获相应授权。[数据集](https://github.com/ubisoft/ubisoft-laforge-animation-dataset) · [官方许可](https://github.com/ubisoft/ubisoft-laforge-animation-dataset/blob/master/license.txt)

本包使用内置 **Dex V8 的 LAFAN1 分支**，入口为 `dex-sm data convert --dataset lafan1`，不经过 SOMA 映射或旧 GMR 转换脚本。该分支使用 LAFAN1 的人体局部轴与骨盆朝向校准，并依据 Ubisoft 官方参考人体鞋底表面建立固定鞋底法向、脚跟和前掌点；转换前校验 Toe 相对 Foot 的固定旋转、骨架层级和踝到趾尺寸，不从动作估计足底朝向。没有站立、全程腾空、摔倒或躺卧都不影响同一骨架标定。

目录建议 `raw/`、`sources.jsonl`、`processed_v8_constrained/`、`release_v8_constrained/`，与 BONES-SEED 分开。LAFAN1 是独立可选数据，不属于 12341 主数据，也不会自动混入新的 BONES-SEED release。旧 LAFAN1 转换数据应从 BVH 重做，旧 A 级标签不作为 V8 准入依据。清单字段见 [数据协议](../README.md)。

## 准备本地人体几何

从官方仓库获取 Git LFS 中的 `fbx/model_skeleton.fbx` 完整文件。提取器检查其 SHA-256 为 `3d9349b5ec686248be6ab73ea3b918f486016a0d22e4b4b80d5418c8f3a608aa`。安装 `.[convert]`，准备 C 编译器 `cc`，并下载固定版本的 ufbx 源码与 LICENSE。

在本项目根目录执行以下命令。

```bash
git clone https://github.com/ufbx/ufbx.git data/lafan1/local_geometry/ufbx
git -C data/lafan1/local_geometry/ufbx checkout 5955c5c0b042ac2dc6f32955ab206aaec0620cfc
dex-sm data prepare-lafan-geometry \
  --fbx /path/to/ubisoft-laforge-animation-dataset/fbx/model_skeleton.fbx \
  --ufbx-dir data/lafan1/local_geometry/ufbx
```

默认输出为 `data/lafan1/local_geometry/lafan1_surfaces.json`。准备命令校验 ufbx 源码版本后编译提取器，生成骨段表面、鞋底法向和脚跟/前掌点。

使用自定义缓存时，先设置路径，再运行准备和转换命令。

```bash
export DEX_LAFAN_GEOMETRY=/path/to/local/lafan1_surfaces.json
dex-sm data prepare-lafan-geometry --fbx /path/to/model_skeleton.fbx --ufbx-dir /path/to/ufbx
dex-sm data convert --dataset lafan1 --manifest data/lafan1/sources.jsonl --out data/lafan1/processed_v8_constrained --workers 1
```

通过已安装 wheel 从其他目录运行时，设置 `DEX_SUPERMIMIC_ROOT` 指向含机器人资产的工作区，或使用 `DEX_ASSETS` 和 `DEX_LAFAN_GEOMETRY` 显式指定路径。缺少本地几何时，转换入口会报告准备命令。几何文件的内容哈希参与转换身份校验，移动相同文件可复用同一身份，修改几何后需重新转换。

已有几何文件会在读取时校验原始 FBX 哈希、结构和有限数值。
