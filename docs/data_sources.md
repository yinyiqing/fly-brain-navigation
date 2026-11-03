# FlyWire v783 数据来源

## 连接组

- 名称：FlyWire Whole-brain Connectome Connectivity Data。
- 发布者：FlyWire Consortium。
- 版本：783.0，即 FAFB materialization 783。
- 固定存档：https://doi.org/10.5281/zenodo.10676866 。
- 访问日期：2026-11-03。
- 本次抓取的 Zenodo 元数据标注许可为 CC BY 4.0，原始元数据保存在 `data/metadata/zenodo_10676866.json`。这条许可记录不自动适用于其他来源的文件。

下载的 `proofread_connections_783.feather` 是校对神经元之间的全脑连接表。每一行对应一个突触前神经元、突触后神经元和脑区的组合，`syn_count` 是该组合的突触数量。原始发布保留至少一个突触的组合，本次没有额外施加“五个突触以上”等阈值。

`proofread_root_ids_783.npy` 是同一发布的校对神经元 ID 数组。ID 必须作为整数读取，不能通过浮点数中转。

## 神经元注释

- 仓库：https://github.com/flyconnectome/flywire_annotations 。
- 固定版本：https://github.com/flyconnectome/flywire_annotations/releases/tag/v2.1.0 。
- 固定提交：`ebd66db2596fcc39c6950fb54ea3efa00f7fe8a0`。
- 原路径：`supplemental_files/Supplemental_file1_neuron_annotations.tsv`。
- 本地文件：`data/raw/flywire_783/neuron_annotations_v2.1.0.tsv`。

作者说明 v2.1.0 对应 Schlegel 等和 Dorkenwald 等 2024 年论文，并使用 v783 root ID。这里固定这个版本，避免后续注释更新导致实验结果难以复现。它不是该仓库的最新注释版本。

原始 README 和字段说明已保存到 `data/metadata/`。注释包含细胞类型、脑区类别、侧别、递质预测等。`top_nt` 是预测结果；将其映射为兴奋性或抑制性权重仍属于模型假设，不能直接视为已知生理事实。

GitHub 固定标签树中没有独立 LICENSE 文件，本次未单独确认注释文件的再分发许可。后续发表或再分发时应以作者条款为准，并保留原始引用。

## 本次未下载的数据

未下载约 9.5 GB 的 `flywire_synapses_783.feather`。它是约 1.3 亿条突触的坐标与预测明细，其中含有不属于校对神经元集合的端点；它的统计口径不同于任务书中的约 5000 万条全脑校对连接突触。

当前计划中的点神经元网络仿真使用连接数量即可，不需要每个突触的空间坐标。因此本次保留完整校对连接图，省去逐突触坐标、神经元骨架、NBLAST 矩阵和电镜图像。若后续明确研究突触空间位置或细胞形态，再按需追加。

## 完整性与统计

`data/sources.json` 固定文件来源、预期字节数及原始校验值。Zenodo 文件使用发布方 MD5，GitHub 文件使用固定 Git blob SHA-1；下载完成后另外计算 SHA-256。

`scripts/inspect_data.py` 分批读取 Feather 文件，核对突触前后 ID 是否属于校对集合、计数是否为正、注释 ID 是否重复，并输出实际统计。连接表行数不是突触总数，突触总数应对 `syn_count` 求和。

论文引用见 `references.bib`，完整上游数据来源说明见 Zenodo 原始元数据。
