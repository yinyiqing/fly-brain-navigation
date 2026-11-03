# Brian2 公开基础模型

已拉取论文作者的公开原版 `philshiu/Drosophila_brain_model`。这是可核验的公共模型，尚未确认它与老师可能维护的课程公共仓库是否相同。

## 来源和版本

- GitHub：https://github.com/philshiu/Drosophila_brain_model
- 正式论文：Shiu 等，A Drosophila computational brain model reveals sensorimotor processing，Nature，2024。
- 论文 DOI：https://doi.org/10.1038/s41586-024-07763-9
- 论文的 Code availability 直接指向上述 GitHub 仓库。
- 固定提交：`91bdd1e7dcf193f3e7ca5a8933497fcef63b7960`。
- 远程位置：`/home/jiutian/projects/fly-brain-navigation/external/Drosophila_brain_model`。
- 代码许可：仓库附带 MIT License；数据另按其来源条款处理。

本次使用稀疏检出，保留模型、工具、例子、环境文件、许可和 v783 输入。原版代码没有改动，来源和提交保存在项目根目录 `upstream.lock.json`。第三方仓库由自己的 Git 管理，已排除在外层项目的普通文件追踪之外。

## 已有功能

`model.py` 使用 Brian2 实现泄漏积分发放（LIF）神经元及突触网络。通过 FlyWire neuron ID 指定刺激或抑制对象，输出放电时间和频率。`utils.py` 提供结果读取和放电频率统计，`example.ipynb` 提供示例。

原版没有现成的运动环境、路径积分任务或归巢控制器。本课题只补充完成单体小实验所需的任务与神经接口；多智能体通信不在本次交付范围内。

## 使用 v783

原始示例默认使用 v630。仓库 README 明确提供 v783 的输入配置：

- `Completeness_783.csv`：模型神经元列表，CSV 行序决定 Brian2 神经元索引。
- `Connectivity_783.parquet`：配套连接表，含 `Presynaptic_Index`、`Postsynaptic_Index` 和 `Excitatory x Connectivity`。

这些索引必须与配套 CSV 保持一致，不能单独重新排序或换成原始 ID 数组。模型将作者提供的带正负号连接值乘以 `w_syn` 作为权重；正负号是模型处理结果，不能误称为每条突触的实测效应。

本次校验了所选文件的 Git blob 哈希，检查了所有连接索引的范围及 ID 映射，未发现错误。数据数量如下：

| 项目 | 数量 |
| --- | ---: |
| 原始 v783 校对神经元 | 139,255 |
| 作者模型中的神经元 | 138,639 |
| 原始集合中未被模型保留的神经元 | 616 |
| 作者模型连接记录 | 15,091,983 |
| 带正负号连接值的绝对值之和 | 54,492,922 |

经逐批检查，上述 616 个未保留神经元没有出现在原始校对连接表的任何端点中；模型没有额外引入原始集合之外的神经元。原始连接表按神经元对和脑区列记录，作者模型不保留脑区这一粒度，因此两者记录数不同。突触总量一致；本次没有逐对重建并比较所有权重，也没有据此宣称完成原论文复现。

## 环境和验证边界

上游 `environment.yml` 指定 Python 3.10、Brian2 2.5.1、NumPy 1.24，并依赖 pandas、joblib、PyArrow 等。`environment_full.yml` 是作者原实验更详细的环境记录，部分版本与精简环境文件不同。

`.venv-data` 使用 Python 3.13，只负责数据处理。另已建立 Python 3.10 的 `.venv-sim`，安装固定版本的 Brian2 2.5.1 等依赖，并于 2026-11-03 通过真实 CX 子网络与完整 v783 模型的各一次 100 ms 试验。运行记录见 `docs/runtime_validation.md`。随后已实现人工方向编码、CX 放电读出和外部路径积分组成的简化归巢实验，见 README；这不构成原版连接组自主归巢能力的验证。

原版 `run_exp` 默认 `n_proc=-1`，且默认重复 30 次；首次试运行应明确使用 `n_proc=1`、一次短时实验。该原版采用 CPU 仿真，存在 RTX 4090 不代表它会自动使用 GPU。

本次简化任务的实现与结果见 `examples/coursework-20261103/`，范围及限制见 `docs/experiment_plan.md`。
