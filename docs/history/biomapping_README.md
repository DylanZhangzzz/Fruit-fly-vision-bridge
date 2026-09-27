> Historical laboratory notes, preserved for context. Commands and relative paths below describe earlier local runs, not the release quickstart. Use [current installation](../installation.md) and [findings](../findings.md).

# 生物视野映射：参考眼原型与 MaleCNS 对应验证

## 最新生理验证（2026-09-27）

已完成公开 L2 活体电压指示器数据的逐记录分析：214 个 ROI 记录全部可查看，主要分析使用作者选中的 103 个记录、13 只果蝇。核查发现其均值就是此前作者的拟合数据，因此单独标记历史复现；新增按整只果蝇留出的交叉验证，所有参数、尺度和延迟只由其余果蝇确定。平均逐蝇 r=0.750、RMSE=0.00663 ΔF/F，5 个主要记录 R² 为负。报告：`physiology_validation/index.html`；复现与边界见 `physiology_validation/README.md`。

这是同研究、同一种 20 ms 全屏闪光的跨果蝇预测，尚不是独立研究、空间感受野或 MaleCNS ID 验证。多个参数触及预设边界；对训练均值波形模板的优势很小，不声称生物参数已唯一确定。没有替换 BrainCPU 的工程输入。下文保留各早期阶段的实现与限制，约 5 Hz 指早期快照存档；后续拍屏工程验收已使用约 59.5 Hz RGB。

## 已完成与未完成

已从 Zhao et al. 2025 官方代码固定版本导出 **778 条右眼视柱—视线记录**，保留 Mi1 源索引、透镜索引、规则网格、三维单位方向和角度。它是作者依据 FAFB 雌蝇神经结构与微 CT 眼睛建立的跨标本参考映射，不是 778 个当前 MaleCNS 神经元，也不是每个神经元的生理实测感受野。

已找到 eyemap_T4 维护者 Arthur Zhao（artxz）另行公开的 **eyemap-archive**。其中 MaleCNS 右眼原始 XLSX 同时给出 `hex1/hex2`、`p/q` 和 `x/y/z/theta/phi`，可以按确切视柱键连接到 MaleCNS L2，无需自行拟合跨标本仿射。

实际结果：**847/893 个 L2 已连接到作者发布的方向，对应 846 个唯一视柱；46 个边缘 L2 无方向，保持空缺，不外推。** 43130 和 56150 同属 (25,10)，方向相同。完整新表为 `data/malecns_author_crosswalk.json`，原 `data/malecns_crosswalk.json` 保留为之前仅含身份核对的历史输入。

源表采用 x 向前、y 向左、z 向上；其 phi 是向右为正，因此本项目方位角为 `-phi`，仰角为 `90-theta`。源表自带的 `p=hex2-19, q=hex1-18` 关系已核对。保留 XLSX 原精度，不以六位小数 CSV 替代单位向量。

17 项自动测试通过。新映射已使用保存的 RGB-D-IMU 记录回放并接入未修改的 BrainCPU，全脑零输入/正常连接/断连对照通过。RGB 的 `120*(1-L)` Hz 仍是工程刺激，不是生理 L2 响应。作者映射也是跨标本解剖预测，不能宣称逐神经元生理实测。相机安装朝向与 IMU 同步仍有已声明的假设。

## 三种输入的用途

- **RGB**：沿生物参考视线采样亮度。相机视野之外为未知，不是黑色，不把复眼全视野压缩到摄像头窄视野。当前中心射线采样未包含复眼接受角、光谱响应、光适应、ON/OFF 和 L2 时间滤波。
- **深度**：由原始深度经过真实外参到彩色坐标，提供可见表面、遮挡和后续平移视差验证。无效深度不抹去已观测 RGB；深度不作为新增“果蝇测距感官”，不直接增强神经放电。
- **IMU**：旋转到彩色相机坐标，依据 -ω×视线 预测纯旋转光流。用于区分相机自转和物体/平移运动，不注入不存在的果蝇 IMU 神经元。当前未做偏置校正、时间延迟标定或绝对航向恢复。

视频和 IMU 本次设备返回不同时间戳域。采集保存 SDK 时间戳、时钟域和主机接收时间；同域时用 SDK 时间窗，否则仅用主机接收时间近似配对并标记。主机接收不等于传感器曝光时间，近似配对不能用于宣称精确同步。所有原始值都保留，以便后续估计固定偏移与抖动。

坐标统一为右手系：头/眼 x 向前、y 向左、z 向上，正方位角向左；相机 x 向右、y 向下、z 向前。默认相机朝前只是台架安装假设；不能用重力自动确定果蝇头部坐标。原始 IMU 已由 SDK 处理，不能再次施加芯片到深度相机的内部变换；这里只用流之间的 SDK 外参。

## 可重复运行

在项目根目录使用现有 .venv-realsense 环境：

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/biomapping/import_atlas.py
& '.\.venv-realsense\Scripts\python.exe' camera_lab/biomapping/test_biomapping.py
& '.\.venv-realsense\Scripts\python.exe' camera_lab/biomapping/capture_multimodal.py
& '.\.venv-realsense\Scripts\python.exe' camera_lab/biomapping/run_reference.py 'camera_lab/biomapping/captures/实际目录'
```

采集预热后录制约 5 秒，视频下采样保存约 5 Hz，IMU 保留原采样，随后释放相机；不上传图像。回放输出 reference_eye/index.html、逐视线 channels.json 和 report.json。当前使用快照中的出厂相机参数；此前棋盘候选尚未应用。rdata 1.1.0 用于读取官方 RData，原始文件与 GPL-3.0 LICENSE 一起保存在 source，哈希见 data/provenance.json。

## 作者映射复现

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/biomapping/run_malecns.py camera_lab/biomapping/captures/20260927-121853-795739
```

该命令重建精确对应、运行 17 项测试、投影当前保存快照、生成工程 L2 输入、运行全脑三个对照并生成 `malecns_eye/index.html` 和逐神经元检查 CSV。847 个目标都处于自身球面点刺激的峰值，其中 845 个独立可分，两个共享视柱不可分。视野外及缺失角度位置不会被当作黑色输入。

作者结果固定在 `503c7f055d5491a48b60b49ade8c71798d24d8f1`；文件及 SHA-256 见 `data/author_mapping_report.json`。源数据和衍生对应表按 CC BY-SA 4.0 标注，作者许可证保存在 source/eyemap_archive/LICENSE。作者 README 明确说明生成映射的 R_eyemap-DIY 流水线仍私有，但结果公开。这里使用作者发布结果，未复现其私有配准算法。

`register_landmarks.py` 保留为替代实验工具；当前正式接线不经过它，不需要用户自己提供解剖标志。

## 完成映射后的验证协议

| 层级 | 实验与独立依据 | 记录 | 目前状态 |
|---|---|---|---|
| 生物身份/方向 | 证据支持的视柱标志；独立保留标志 | 每细胞来源、球面角误差、未知/歧义 | 作者精确视柱连接 847 个 L2；46 个空缺；不是生理实测 |
| 几何实现 | 已知射线、方向翻转故障、视野外输入 | 像素/角度误差，未知不能变黑 | 合成测试通过 |
| 接受角与动态编码 | 论文或独立实测的点/条纹/ON-OFF/频率响应 | 感受野宽度、延迟、时间常数 | 尚未实现，不能复用任意 120*(1-L) 冒充 |
| RGB + IMU 纯转动 | 固定场景、绕光心转动，独立视觉跟踪 | 实测光流与 -ω×r 比较；时间偏移单独估计 | 已输出预测，真实运动验证待做 |
| 深度 + 平移 | 近远不透明靶标，已知位移或视觉里程计 | 平移视差近大远小、遮挡与空洞 | 合成几何通过，实物精度待验证 |
| 混合运动对照 | 相机固定/物体动，与物体固定/相机动成对采集 | 去除旋转预测后的残差；不能把残差全归平移 | 待独立录制 |
| 网络功能 | 正确映射、打乱、翻转、零输入、断连，多随机种子 | 输入层与下游分开评估，位置/运动解码留出测试集 | 作者映射点寻址及一次快照的零输入/正常/断连通过；运动解码未验证 |

必须先冻结映射，再使用未参与拟合的空间区域与运动片段验证。输入采样成功、网络放电或拟合误差低，都不能单独证明生物正确。单台 D435i 不能观测整只复眼；多相机需要另外的外参和同步，IMU 不能凭空补全未拍到的视野。

## 主要来源

- Zhao et al., Nature 2025: https://www.nature.com/articles/s41586-025-09276-5
- 官方视野数据和坐标处理：https://github.com/reiserlab/eyemap_T4/tree/99d2a43123db636cedb55af9ff31a59657e7d17e
- MaleCNS 视通路代码：https://github.com/reiserlab/visualpathways/tree/23f6ac131529b5f56894c6eeb9b88b17894fc00d

来源核对结论仅限已查看的论文、源表与代码，不声称其他公开或未公开资源不存在可用对应。

- 作者额外发布的 MaleCNS 方向表：https://github.com/artxz/eyemap-archive/tree/503c7f055d5491a48b60b49ade8c71798d24d8f1
- MaleCNS 论文说明扩展了 Zhao 眼图：https://doi.org/10.1016/j.cell.2026.08.015


## L2 temporal-response validation

Run `python camera_lab/biomapping/validate_l2_dynamics.py`. Results: `temporal_validation/index.html`. Reimplements the published recurrent equations using rounded fitted parameters from ClandininLab/L1L2-deblur commit 7fa5829e37d566e02beaaa87efd6a0f1de4e48c0. High-luminance reproduction r=0.9658; low-luminance no-refit comparison r=0.8629. High data were used by the authors for fitting; this is not independent validation. Sign and rebound checks pass. Moving-bar and frequency outputs are predictions only. Output is a voltage-indicator proxy, not calibrated mV or Hz. Existing BrainCPU input remains unchanged. Saved camera sampling near 5 Hz is insufficient for millisecond response validation. Source files and hashes are preserved in the report.
