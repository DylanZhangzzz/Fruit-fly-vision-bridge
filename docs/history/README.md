> Historical laboratory notes, preserved for context. Commands and relative paths below describe earlier local runs, not the release quickstart. Use [current installation](../installation.md) and [findings](../findings.md).

# D435i 视觉实验：采集验证

已实现第一版单帧 RGB-D → 空间编码 → 完整 MaleCNS 连接网络回放。它使用现有 Xenova BrainCPU，不是新安装的 Shiu 原始 Brian2 后端；原模型文件没有修改。尚未实现持续实时输入或生物视觉验证。

## 运行一次完整实验

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/run_snapshot.py
```

自动短时采集、释放相机、编码、运行 50 ms 模型时间及两个对照，最后输出 experiment.html 的位置。双击 HTML 查看报告。可传入已有 capture 目录进行同样的离线回放。

## 编码设计与限制

1. 从原始深度逐像素反投影到米制三维点，再应用深度到 RGB 外参，得到彩色相机坐标。修正了旧版将 SDK 对齐深度直接视作彩色相机 Z 的近似。保留全部原始深度像素，投影到同一彩色像素时选最近点。
2. 将点投影到平移 3 cm 的平行虚拟视点，采用最近点遮挡处理。这是可调的台架实验设置，不是果蝇眼距；深度并不直接放大刺激强度。
3. 读取 Reiser lab 的 ME_assigned_columns.csv，按 body ID、类型及右眼标签核对，匹配到 893 个 L2 神经元。公开网格保留相对空间位置；hex 网格到相机视野的朝向、尺度是人为设定，尚未得到角度标定。
4. 每个位置统计局部有效亮度，使用 120*(1-luminance) Hz 的工程映射刺激 L2。绕过感光细胞，因为当前模型的 histamine 快信号为零。此映射不是经过验证的 L2 光响应；无效深度没有补成近物体，采样不足时零输入。
5. 原封不动加载现有 166,700 神经元、25,582,938 有向连接的 BrainCPU。每个连接数据块核对原 manifest 的 SHA-256；输入 body ID 和类型再次核对。

单帧固定输入保持 50 ms，不代表动态视觉、物体识别或距离解码。透明瓶身的错误非零深度依然可能进入编码；深度参考也不是绝对真值。没有根据神经元胞体坐标推断它的视野位置。

### 验证

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/test_encoding.py
```

4 个几何测试覆盖：同一射线在零平移下不因深度改变方向；视点平移后近点视差更大；遮挡时近点胜出且空洞保留；无效三维点被过滤。

每次模型实验同时运行 no_input、camera、connections_off，固定种子和初态。20260927-101047-317843 中：无输入 0 次放电；相机输入总放电 5585、活跃 2532 个神经元、下游放电 2930；关闭连接后的下游放电 0。只证明传播路径打通，不证明编码生物学正确。

### 来源

- 视柱表：https://github.com/reiserlab/male-drosophila-visual-system-connectome-code/blob/main/results/exchange/ME_assigned_columns.csv
- 坐标说明：https://github.com/reiserlab/male-drosophila-visual-system-connectome-code/blob/main/docs/coordinate-systems.md
- 数据来源及本地表 SHA-256 记录在 data/provenance.json；原仓库标注 GPL-3.0，继续分发前需保留并遵循原始许可。
- 模拟器和数据来自 ../fruit-fly-simulation，保留原仓库许可证及数据声明。

## 运行

从项目根目录的 PowerShell 执行：

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/probe_camera.py
```

使用独立虚拟环境，pyrealsense2 版本为 2.58.4.10922；NumPy 和 Pillow 继承本机已有运行环境。
程序选择第一台 RealSense，预热 30 帧，采集检查 90 组 640×480 / 30 fps RGB-D 帧，结束后释放设备。
只保存最后一组图像，以及全部检查帧的编号和时间戳；不保存连续视频，不上传相机数据。

## 输出

- rgb.png：RGB 图像。
- depth_raw_u16.png：原始 16 位深度，乘 report.json 中的 depth_scale_m 得到米；0 表示无有效深度。
- depth_aligned_u16.png：重投影到 RGB 像素坐标的深度。
- preview.png：左侧 RGB，右侧深度示意色图（0～3 米截断显示，黑色为无效值）。
- report.json：设备、内外参、深度单位、帧编号、时间戳及采集统计。

## 已完成验证

2026-09-27 检测到一台 D435i，USB 3.2，固件 5.16.0.1。
90 组帧耗时 3.002 秒（29.98 组/秒）；RGB 和深度各有 90 个不同帧编号。
最后一帧原始有效深度占比 85.70%，对齐后占比 93.31%。
两者视野和采样不同，有效率不能直接作为对齐改善精度的证据。
预览已检查，能看到对应的前景轮廓；尚未进行独立标定精度或深度误差验证。

## 下一阶段

先使用可重复的合成运动刺激检查视觉编码，再接入录制的相机片段。
保留像素空间位置；图像送入视觉模型，深度只作为独立的运动/距离验证参考。
记录静止、左右移动、接近/远离、亮度变化等对照，划分调参和测试片段。
FlyVis 与全脑模型的细胞映射和动力学接口需要单独验证，不能假定直接兼容。


## 逐神经元位置审计

从项目根目录执行 `.venv-realsense/Scripts/python.exe camera_lab/run_validation.py`。固定回放快照 20260927-101047-317843，不打开相机。重跑几何、893 次局部刺激、故障注入、893 个网络单点连接开/关测试，生成 validation/index.html 与 reproducibility.json。

报告支持 body ID 查询和异常筛选。891 个位置可独立区分，2 个共用源视柱；893 个地址通过断连对照，887 个在指定条件下观察到传播。生物视野角度均为 UNVERIFIED。来源、假设和限制见 validation/SOURCES_AND_LIMITS.md。
