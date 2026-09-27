> 发布归档：先按 [安装说明](../../docs/installation.md) 安装并获取数据。以下 source/、协议和命令路径以仓库 camera_lab/biomapping/ 为基准。原始分析代码哈希保留为历史证据；当前发布版复现见 ../reproduction/。

# L2 逐记录、留一果蝇生理验证

报告入口：`index.html`。这是同一研究、同一种刺激下的跨果蝇预测检验，未声称独立研究验证、MaleCNS ID 验证或全脑验证。

## 重现

从项目根目录运行：

```powershell
python camera_lab/biomapping/test_l2_cells.py
python camera_lab/biomapping/validate_l2_cells.py
```

依赖：NumPy、SciPy、pandas、openpyxl、matplotlib，以及本次安装的 h5py 3.16.0。脚本只读取公开文件，不启用相机，不上传数据，不修改 BrainCPU 输入。

## 数据与许可

来源：Pang et al., *A recurrent neural circuit in Drosophila temporally sharpens visual inputs*, Current Biology (2025)。DOI: `10.1016/j.cub.2024.11.064`。

- 官方数据：[Dryad](https://datadryad.org/dataset/doi:10.5061/dryad.ngf1vhj4c)，CC0 1.0。
- 已下载 `source/L2_Dryad/L2_ASAP2f.mat`、`L1L2_Metadata.xlsx`、`README.md`。三份文件都与官方 API 提供的 SHA-256 一致，完整来源记录在该目录的 `manifest.json`。
- 原方程与分析方法：[ClandininLab/L1L2-recurrent-feedback](https://github.com/ClandininLab/L1L2-recurrent-feedback/tree/7fa5829e37d566e02beaaa87efd6a0f1de4e48c0)。该固定版本未发现明确许可证；作者 MATLAB 代码和 notebook 不包含在本发布中。这里的 Python 实现、分箱数值和论文参数均注明来源，不能据此推断作者源代码可再分发。
- 现有相机工程验收：[固定标定、独立时序报告](../screen/README.md)。该结论不等于神经生理验证。

## 数据审计

共有 214 个 ROI 记录，分属 MAT 中 14 个果蝇编号。作者按独立搜索刺激选出的 103 个记录、13 只果蝇用于主要分析；其余 111 个记录保持可查看，作为敏感性分析。ROI 记录不等同于确认互不重复的细胞，更不等同于 MaleCNS bodyId。

103 个记录的平均响应与先前 GitHub 的 `L2_highLum.mat` 完全一致。因此，已发表参数套用到这些记录的结果属于训练数据复现。本报告另做按整只果蝇划分的交叉验证。

工作簿与 MAT 使用不同编号。35 个记录的系列名重排，28 个若直接按系列名连接会接到不同基因型。通过日期、LDM 序号、成像 Z 深度、基因型与刺激联合匹配到唯一行；主要分析的 13 个 MAT 果蝇分组与元数据果蝇编号一一对应。原编号、匹配后编号及证据保留在 `metadata_crosswalk.csv`。13 个作者未选中记录仍无元数据匹配，不进入主要分析。

从已处理 dF/F 时间序列与刺激转换时间重新分箱，与所有发布平均曲线相差最多约 5.6e-17。保留作者浮点边界运算顺序；直接使用 `ceil(time/dt)` 会在精确边界上改动少数样本的归属。早期分箱故障诊断未纳入此发布归档；最终结果以 report.json 为准。

## 预先固定的分析规则

协议为上级目录 `l2_physiology_protocol.json`，运行时复制为 `protocol.json` 并记录哈希。未按测试结果调整参数边界、训练起点或模型选择标准。

每折仅对其余果蝇的等权平均曲线拟合：循环时间常数、反馈、非对称性、明暗驱动、输出基线与延迟。未拟合被留出细胞的增益、基线或时间平移。13 个有作者选中记录的果蝇构成主要评价；第 14 折只生成作者未选中记录的次要预测。

方程族来自论文，本次改为数值积分名义 20 ms 刺激，并按官方尾随 8.33 ms 时间窗平均，以与记录处理一致。旧作者离散模型的 3 个 120 Hz 采样点脉冲（25 ms 近似）只用于单独的历史复现字段。输出是有效的电压指示器荧光代理，没有新建从 mV 到 ASAP2f 荧光的标定模型。

无反馈动力学也在训练集上独立拟合；另比较训练均值波形模板和常数基线。RMSE 与 R² 都使用未经逐测试细胞调整的预测。相关系数不是 R²。负 R² 保留，并不改名为通过。

奇偶次闪光各自重新分箱，报告重复可靠性。bootstrap 按果蝇采样，13 只果蝇等权；由于各折训练集重叠，区间是描述性的，不作为外部验证的显著性结论。

## 结果边界

结果详见 `report.json`。多个反馈参数到达预设边界，说明当前刺激与参数化不足以唯一确定生理参数；不因边界命中就扩大搜索范围以美化本次结果。模型对跨果蝇平均波形模板的优势很小，不能从这组数据推断自然场景或新刺激泛化。

这不是重新处理原始显微镜图像，也不是实测绝对电压或放电率。光谱、适应、感受野位置、相机辐射定标和全脑传播均不在本报告验证范围内。

## 输出

- `cells.csv` / `cells.json`：全部 214 个记录，明暗分别评分，峰值/反弹/时间误差、重复可靠性与来源。
- `folds.json`：每折训练/测试编号、拟合参数、收敛信息和边界检查。
- `response_traces.npz`：实测、奇偶重复、四类留出预测以及固定作者参数复现。
- `metadata_crosswalk.csv`：元数据对应审计。
- `index.html`：可筛选并逐个切换曲线的离线报告，无 CDN。
