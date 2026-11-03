# 数据目录

BONES / LAFAN 训练集仅保存获取说明；三段外部演示动作的实际文件也未随仓库发布，当前没有完整数据附件。训练和评估前需自行取得或生成相应数据。`bones_seed/` 为主体训练数据；`lafan1/` 是独立可选补充；`evaluation/` 放外部开发动作。原始人体、重定向机器人、特征缓存三类文件不能混用。

转换入口接受 JSONL，每行示例：

```json
{"id":"unique_clip_id","source":"raw/Dances/example.bvh","actor":"actor_01","sampling_group":"dance","anchor":false,"evaluation_only":false}
```

`source` 相对 JSONL 所在目录；`id` 只能含字母数字、下划线和横线，并且全局唯一。`actor` 从数据元数据填写；`sampling_group` 必须是 `dance / locomotion / stationary_upper / dynamic`，依据动作元数据分类。不能把所有 Gaming 都当舞蹈，也不要为未知演员虚造不同 ID。完整来源清单、下载校验和类别映射应随本地数据归档。

历史转换记录只要具备 `id/output/output_sha256/frames/grade/actor/sampling_group/anchor` 可供 `data build` 读取。A 级全部进入训练；带 `evaluation_only=true` 的记录会被拒绝。外部评估数据放在独立目录并排除在训练 manifest 之外。

```text
bones_seed/
  sources.jsonl          # 冻结来源清单和分类
  raw/                  # SOMA Uniform BVH
  processed/
    records/            # 来源哈希、IK 审计、等级、失败原因
    motions/            # 无损压缩的 root + joints NPZ
    work/               # 机器人 PKL、完整 FK NPZ 与排错中间件
    status.json
  release/
    manifest.json
    shard_000.json
    features/index.json
    features/shard_000.pt
```

转换：首帧重复预热，检测根速度收敛后移除预热帧，保留原动作时间；GMR 速度与碰撞约束；转换 50 Hz；格式/关节/模型检查；再做脚部穿透、静态悬空、根速度突变和 IK 恢复等筛选。A 为运动学候选，B 需修复，C 转换失败；筛选未验证控制器动态可跟踪性。

`data convert` 默认最多 8 个独立 CPU worker，每个数值库单线程；可调 `--workers`。来源/产物哈希一致时复用转换产物，但演员、分类、锚点、`evaluation_only` 等元数据以本轮清单为准，并写回记录；标成评估用途后，`train_eligible` 同步为 false。清单不可提供 `grade`、`output`、`train_eligible` 等由转换器生成的字段。

本轮来源清单记录为 `catalog.json`。构建只接收该清单中的记录，检查元数据指纹并拒绝未完成的转换目录；从清单删除的旧记录不会重新进入训练。A 级中若有 `evaluation_only=true`，构建会明确拒绝。历史无 catalog 的记录目录仍支持显式导入，但应先用原来源清单再跑一次 `data convert` 以建立当前身份和标签；哈希匹配的产物无需重新 IK。

失败记录保留，修复后应使用新的输出目录或明确处理失败记录。中间文件便于诊断，可在归档核验后自行清理；脚本不会删除原始资料。

`data build` 固定排序、保持整段、不切掉长动作。片段与锚点超出容量时明确失败，需提高容量或另行定义带来源关系的切片规则。缓存检查原始 NPZ 哈希、边界帧 goal 一致性，并记录机器人和特征代码哈希。

已有合格 release 可 `dex-sm data import --source ... --out ...` 导入：先校验所有分片与 manifest，再把索引改为相对位置。默认链接大文件以节省磁盘；要做独立可搬迁的数据包请加 `--copy-packs`。链接模式不能删除源缓存。旧 shard 内来源路径是审计信息，训练读取已验证 feature pack，不依赖那些旧 NPZ 路径。
