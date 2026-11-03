# Dex 29 关节机器人资产

公开仓库在本目录仅提供本说明，不包含实际机器人资产，也未提供包含资产的 Release 附件。使用源码工作区前，须按下列来源取得匹配资产并导入；导入后保留其原始 LICENSE。

来源：[Dex-Video2Robot](https://github.com/luckylhf/Dex-Video2Robot) 的 `Dex-GMR/assets/dex`，或既有已核验的相同资产目录。按上游许可获得模型，保留其 LICENSE。资产使用 OpenAtom Open Hardware License 1.0，不能用本仓库代码的 MIT 许可替代。

```bash
python scripts/import_assets.py --source /path/to/Dex-Video2Robot/Dex-GMR/assets/dex
```

脚本核对 12341 XML 指纹并编译检查，然后复制 `model.json`、`mjcf/`、`meshes/`、`meshes_visual/`、`meshes_convex/`、`urdf/`、`LICENSE`；产物被 Git 忽略。

所需 XML SHA-256：`17573c55d1c9d9d43b2e44a5e3ebc237027bfcfb6f5b5d928aa0205792548194`。

也可通过 `DEX_ASSETS=/absolute/path/to/assets` 使用外部目录。模型不匹配时，应重新转换、训练和验证；不要只改 JSON 哈希来绕过检查。
