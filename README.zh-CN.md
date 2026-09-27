# Fruit-fly-vision-bridge

[English](README.md) · [当前发现](docs/findings.md) · [安装](docs/installation.md) · [贡献指南](CONTRIBUTING.md)

把相机观测接到有公开生物依据的果蝇视觉位置，并提供可以检查、重跑和质疑的验证流程。

目前包含 Python 代码、D435i RGB/深度/IMU 采集、普通 RGB 相机与图像入口、MaleCNS 视柱对应、屏幕刺激实验、公开 L2 生理记录验证，以及结果报告。它是独立实验项目，不是研究团队官方提供的 webcam API。

## 做到了什么

- 按作者发布的视柱键连接 **847/893 个右眼 L2 ID**，对应 846 个唯一视柱；46 个缺失方向保留为空。来源是跨标本解剖估计，不是逐细胞生理感受野测量。
- 新增左眼独立映射：**847/886 个 L2 ID** 可连接公开视线；32 个缺方向、7 个缺视柱分配，保持未知。两眼合计 1,694 个已映射输入。
- 在固定屏幕、相机和黑白参考块条件下，**21 个 L2 ID / 20 个视柱**通过时序工程验收，RGB 约 59.53 帧/秒。
- 用真实公开成像记录做整只果蝇留出验证：**103 条记录、13 只果蝇**，平均 r=0.750，R²=0.447，RMSE=0.00663 ΔF/F。
- 公开保留 **5 条 R²≤0 的记录**及拟合边界问题。反馈模型好于无反馈对照，但相对其他果蝇平均波形没有明确优势。

这些工作建立了可运行的桥接系统和可复查的证据；尚不能证明完整复现真实果蝇视觉或全脑活动。成像 ROI 不是 MaleCNS 神经元 ID。

## 无需相机，先运行示例

新增[统一离线视觉基准](docs/benchmark.md)：让 L2 固定参数模型、FlyDrones 官方感觉编码器和 Flyvis 官方预训练网络处理同一批闪光、条纹、移动边缘和逼近/远离刺激。下载仓库后可打开[合成输入报告](reports/benchmark/index.html)。已提供 Flyvis L2 到 MaleCNS 采样图像位置的插值读出；这是图像空间适配，尚不是细胞身份对应或新的生理验证。

```powershell
git clone https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge.git
cd Fruit-fly-vision-bridge
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m flyvisionbridge.cli --demo --output outputs/demo
python scripts/run_checks.py --core-only
```

PowerShell 不允许激活脚本时，直接使用 `.venv\Scripts\python.exe` 替代 `python`，不需要修改系统执行策略。Linux/macOS 的激活命令为 `source .venv/bin/activate`；硬件 SDK 的平台支持须另外确认。

示例生成合成图与逐 ID 的 `channels.json`。相机视野外、缺失角度均为未知，不当作黑色。该输出是 RGB 数字亮度，不是放电率。

## 普通 webcam 接入大脑

现在提供完整的 **相机画面 → L2 位置采样 → 工程刺激 → 持续运行的 BrainCPU → 下游活动** 入口：

```powershell
python -m pip install -e ".[analysis]"
python -m flyvisionbridge.live --model-dir PATH_TO_FRUIT_FLY_SIMULATION --device-name "Logitech BRIO" --assume-hfov 90
```

按[实时接入说明](docs/webcam-live.md)安装 Node.js、独立模型和 FFmpeg 后，打开 `http://127.0.0.1:8771/`，点击“开始采集”。普通 OpenCV 相机可改用 `--camera 0`；必须提供内参或明确指定临时视场假设。这里的 90° 不是 BRIO 实测标定值。

实时入口现在默认接入**双眼**，可用 `--eyes left/right/both` 分别选择（命令中填写其中一个值）。左眼按独立公开表精确连接 847/886 个 L2，39 个缺失条目保持未知。已有 BRIO 图像的完整模型重放覆盖左眼 229＋右眼 217 个输入；双眼新版尚未完成新一轮实机采集。详见[双眼接入与验证](docs/binocular.md)。

此前已用 Windows 上的 BRIO 完成右眼实机运行：217 个可见 L2 输入接入 166,700 个神经元的完整网络；连续帧保留模型状态，零输入、断连和减半输入对照通过。默认每秒更新 5 次，每次推进 20 ms 模型时间，约为现实时间的 0.1 倍。详见[硬件验收结果](reports/webcam/README.md)。这里验证的是工程链路，使用显式的亮度到刺激近似。

## 完整流程

1. [安装依赖与获取公开数据](docs/installation.md)：数据固定版本并校验 SHA-256；大型生理文件单独获取。
2. [接入 D435i 或其他相机](docs/cameras.md)：D435i 已有实验记录；BRIO 的 FFmpeg 接入已通过实机工程检查，OpenCV 后端仍需单独实测。没有深度/IMU 的相机明确输出缺失。
3. [重建映射](docs/mapping.md)：说明视柱来源、坐标变换、空缺及共享位置。
4. [运行验证](docs/validation.md)：区分合成实现检查、相机工程验收和生理预测。
5. [查看报告](reports/index.html)：下载仓库后打开，或运行 `python -m http.server 8000 --bind 127.0.0.1`，访问 `http://127.0.0.1:8000/reports/`。

RGB 用于观测亮度，深度辅助几何与遮挡，IMU 辅助旋转光流预测。深度与 IMU 不会直接成为额外的果蝇感官。原始录像和设备序列号不随仓库发布。

下一阶段是固定参数后，预测未用于拟合的刺激持续时间、频率或对比度，并与独立生理记录比较。这项工作目前列在 [路线图](docs/roadmap.md)，没有标记为完成。

欢迎通过 [Issues](https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge/issues) 提问题，用中文或英文均可；贡献代码请看 [CONTRIBUTING.md](CONTRIBUTING.md)。代码采用 GPL-3.0-only；第三方数据保留原许可，详见 [来源与许可](THIRD_PARTY_NOTICES.md)。

[发布前权利与许可审查](docs/license-review.md)记录已核查的来源、修正项及作者代码/模型权重的授权边界，不构成“绝无侵权”的法律保证。安装包元数据中的 `GPL-3.0-only AND CC-BY-SA-4.0 AND CC-BY-4.0` 描述代码与数据的混合分发，原始项目代码仍为 GPL-3.0-only。
