# Fruit-fly-vision-bridge

**把普通 webcam 接到模拟果蝇大脑，并提供明确的视觉位置映射和可复现的检查。**

这是面向 **Drosophila / MaleCNS** 的 Python 相机桥接项目：把 RGB 图像对应到公开的左、右眼 L2 视线，驱动外部 BrainCPU 模拟器，并查看下游活动。Intel RealSense **D435i** 通过独立的录制与重放流程提供深度和 IMU。当前亮度到神经刺激仍采用工程近似，尚不是经过完整生物验证的视觉响应模型。

[English](README.md) · [无需硬件快速开始](#无需硬件快速开始) · [接入-webcam](#普通-webcam-接入大脑) · [安装](docs/installation.md) · [当前发现](docs/findings.md) · [贡献指南](CONTRIBUTING.md)

![合成 RGB 图像及实际编码器输出的双眼 L2 采样位置：1779 个目标中 211 个可见；缺失方向与视野外通道保持为空。](docs/assets/synthetic-sampling.png)

*由下方合成示例的实际输出生成，使用假设相机内参。蓝色为左眼，橙色为右眼；图中展示 RGB 采样位置，不是神经放电。[重建此图与数据署名](docs/assets/README.md)。*

实时链路为 **相机 RGB → 公开 L2 视线 → 工程刺激 → 持续运行的 BrainCPU → 模拟下游活动**。深度与 IMU 用于辅助几何，普通 webcam 不需要它们。

## 选择你的输入方式

| 输入或流程 | 可以做什么 | 目前验证状态 |
|---|---|---|
| [合成示例](#无需硬件快速开始)或[已有 RGB 图像](docs/cameras.md#saved-images-and-single-frame-rgb-webcam-samples) | 不加载完整大脑，导出逐 ID 亮度与有效性 | 有无需硬件的实现检查 |
| [Windows 上的 Logitech BRIO](#普通-webcam-接入大脑) | 通过 FFmpeg / DirectShow 持续驱动模型 | 右眼实机通过；双眼完整模型重放通过，新一轮双眼采集待完成 |
| [其他 USB 或内置 RGB 摄像头](#普通-webcam-接入大脑) | 通过 OpenCV 相机编号运行同一实时流程 | 适配器已实现，该采集后端尚待实机验证 |
| [Intel RealSense D435i](docs/cameras.md#d435i-recorded-experimental-path) | 录制 RGB、深度和 IMU，重放映射与屏幕实验 | 有几何录制与受控屏幕实验；使用独立于实时 RGB 入口的流程 |
| [离线模型比较](#离线比较视觉编码器) | 比较 L2、FlyDrones、Flyvis 对相同刺激的输出 | 固定协议的合成预测与诊断；可选模型单独安装 |
| [FlyDrones L2 适配器](docs/flydrones.md) | 用公开的逐 body ID 位置替换按索引分配的映射，直接接入 Brain 或 Pilot | [完整原生网络检查](docs/flydrones-full-network.md)：166,700 个神经元、10,520,377 条连接（≥3 突触过滤），双眼输入、因果对照与旧 D435 录像回放；生理真实性仍待验证 |

已提供双眼映射。单个相机只能观测自身视野内的方向，不提供两个实测眼睛原点，也不覆盖完整复眼视野。详见[双眼接入](docs/binocular.md)。

## 无需硬件快速开始

需要 **Python 3.11+ 和 Git**。映射数据已包含；此示例不需要相机、Node.js、RealSense SDK 或完整大脑模型。

```sh
git clone https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge.git
cd Fruit-fly-vision-bridge
python -m venv .venv
```

根据终端选择一条激活命令：

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```sh
# Linux / macOS
source .venv/bin/activate
```

然后运行：

```sh
python -m pip install -e .
python -m flyvisionbridge.cli --demo --eyes both --output outputs/demo
python scripts/run_checks.py --core-only
```

示例预期输出 **`Saved 1779 channels; 211 observed.`**，在 `outputs/demo/` 生成 `rgb.png`、`intrinsics.json` 和 `channels.json`。这组特定合成内参下，左眼 106 个、右眼 105 个通道可见；另外 1,568 个因视野外或方向缺失保持为空。该数量不是相机覆盖上限，示例也不生成放电率。

重复运行请使用新目录，例如 `outputs/demo-02`。若 PowerShell 不允许激活，直接使用 `.venv\Scripts\python.exe` 替代 `python`，无需修改系统执行策略。核心检查会在可选依赖未安装时跳过对应检查；完整测试见[安装说明](docs/installation.md)。

## 普通 webcam 接入大脑

先完成上述环境安装，再按[模型安装步骤](docs/installation.md#reports-and-optional-whole-brain-replay)安装 **Node.js 22.12+、Git LFS 和独立的上游模型**。模型包含较大的下载文件，并保留自身许可。将下方 `PATH_TO_FRUIT_FLY_SIMULATION` 替换为包含 `src/brain.js` 和 `public/data/manifest.json` 的模型目录。

```sh
python -m pip install -e ".[analysis]"
```

**普通 USB 或内置摄像头，使用 OpenCV：**

```sh
python -m flyvisionbridge.live --model-dir PATH_TO_FRUIT_FLY_SIMULATION --camera 0 --assume-hfov 90 --eyes both
```

`0` 是相机编号，请选择目标设备对应的编号。此适配器已实现，下方已有实机记录使用的是 FFmpeg 路线。

**Windows BRIO 的已测试采集路线：**先安装 FFmpeg 并加入 PATH，再运行：

```powershell
python -m flyvisionbridge.live --model-dir PATH_TO_FRUIT_FLY_SIMULATION --device-name "Logitech BRIO" --assume-hfov 90 --eyes both
```

打开 **http://127.0.0.1:8771/**，点击 **开始采集**。默认运行 60 秒，显示输入与下游模拟活动，结束后释放相机；按 Ctrl+C 关闭服务。画面在本机处理，录制保存在 Git 忽略的 `outputs/webcam-live/` 中。

`--assume-hfov 90` 是明确声明的临时视场假设，**不是相机实测标定值**。已有标定内参时，改用 `--intrinsics camera.json`。镜头矫正、设备选择及使用说明见[实时接入指南](docs/webcam-live.md)。

实时入口默认接入双眼；可用 `--eyes left` 或 `--eyes right` 选择单眼。公开表可映射左眼 847/886 个、右眼 847/893 个 L2。已有 BRIO 图像的完整模型重放覆盖左眼 229＋右眼 217 个输入，**双眼新版尚未完成新一轮实机采集**。覆盖量随投影条件变化，详见[双眼证据](docs/binocular.md)。

此前 BRIO/Windows 右眼实机运行向 166,700 个神经元的网络输入了 217 个可见通道，并通过零输入、断连和减半输入对照。默认每秒更新 5 次，每次推进 20 ms 模型时间，名义速度约为现实时间的 **0.1 倍**。面板放电来自模拟器，详见[硬件验收结果](reports/webcam/README.md)。

## 离线比较视觉编码器

[统一离线视觉基准](docs/benchmark.md)让 L2 固定参数模型、FlyDrones 官方感觉编码器和 Flyvis 官方预训练网络处理同一批闪光、条纹、移动边缘和逼近/远离刺激。下载仓库后可打开[合成输入报告](reports/benchmark/index.html)。该可选流程与快速开始示例、实时工程输入规则分别运行。

已提供 Flyvis L2 到 MaleCNS 采样图像位置的插值读出；这是图像空间适配，尚不是细胞身份对应或新的生理验证。

## 做到了什么

- 按作者发布的视柱键连接 **847/893 个右眼 L2 ID**，对应 846 个唯一视柱；46 个缺失方向保留为空。来源是跨标本解剖估计，不是逐细胞生理感受野测量。
- 新增左眼独立映射：**847/886 个 L2 ID** 可连接公开视线；32 个缺方向、7 个缺视柱分配，保持未知。两眼合计 1,694 个已映射输入。
- 在固定屏幕、相机和黑白参考块条件下，**21 个 L2 ID / 20 个视柱**通过时序工程验收，RGB 约 59.53 帧/秒。
- 用真实公开成像记录做整只果蝇留出验证：**103 条记录、13 只果蝇**，平均 r=0.750，R²=0.447，RMSE=0.00663 ΔF/F。
- 公开保留 **5 条 R²≤0 的记录**及拟合边界问题。反馈模型好于无反馈对照，但相对其他果蝇平均波形没有明确优势。

这些工作建立了可运行的桥接系统和可复查的证据；尚不能证明完整复现真实果蝇视觉或全脑活动。成像 ROI 不是 MaleCNS 神经元 ID。

## 完整流程

1. [安装依赖与获取公开数据](docs/installation.md)：数据固定版本并校验 SHA-256；大型生理文件单独获取。
2. [接入 D435i 或其他相机](docs/cameras.md)：D435i 已有实验记录；BRIO 的 FFmpeg 接入已通过实机工程检查，OpenCV 后端仍需单独实测。没有深度/IMU 的相机明确输出缺失。
3. [重建映射](docs/mapping.md)：说明视柱来源、坐标变换、空缺及共享位置。
4. [运行验证](docs/validation.md)：区分合成实现检查、相机工程验收和生理预测。
5. [查看报告](reports/index.html)：下载仓库后打开，或运行 `python -m http.server 8000 --bind 127.0.0.1`，访问 `http://127.0.0.1:8000/reports/`。

RGB 用于观测亮度，深度辅助几何与遮挡，IMU 辅助旋转光流预测。深度与 IMU 不会直接成为额外的果蝇感官。原始录像和设备序列号不随仓库发布。

下一阶段是固定参数后，预测未用于拟合的刺激持续时间、频率或对比度，并与独立生理记录比较。这项工作目前列在 [路线图](docs/roadmap.md)，没有标记为完成。

欢迎通过 [Issues](https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge/issues) 提问题，用中文或英文均可；贡献代码请看 [CONTRIBUTING.md](CONTRIBUTING.md)。

本项目原创代码和文档采用 [MIT 许可证](LICENSE)。第三方代码、映射数据及其衍生数据保留各自的 GPL-3.0、CC BY-SA 4.0、CC BY 4.0 等许可；公开 Dryad 生理数据为 CC0。Python 安装包同时包含代码与映射数据，因此分发元数据列出这些许可的组合，不能把整个数据集重新按 MIT 授权。各文件的适用范围见 [来源与许可](THIRD_PARTY_NOTICES.md)。

[发布前权利与许可审查](docs/license-review.md)记录已核查的来源、修正项及作者代码/模型权重的授权边界，不构成“绝无侵权”的法律保证。安装包元数据中的 `MIT AND GPL-3.0-only AND CC-BY-SA-4.0 AND CC-BY-4.0` 描述代码与数据的混合分发，原创项目代码采用 MIT。
