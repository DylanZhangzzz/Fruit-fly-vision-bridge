> Historical laboratory notes, preserved for context. Commands and relative paths below describe earlier local runs, not the release quickstart. Use [current installation](../installation.md) and [findings](../findings.md).

# 相机与 IMU 标定工具

实现状态：工具可运行，合成真值测试覆盖相机参数恢复、保留视角验证、重复视角拒绝、六姿态 IMU 参数恢复/错误姿态拒绝、标靶检测、深度平面误差与无效深度。尚无真实多姿态数据，因此没有可用的物理标定结果，未修改生产编码或设备参数。

## 显示屏准备

打开 target/screen.html，在相机能够拍到的显示器上点击“全屏展示”。相机必须朝向这块屏幕；当前使用的显示器也可以，但必须能调整相机拍摄它。

全屏后用尺子测量 **9 格棋盘的总宽度**（不含白色外边距），除以 9，得到格长。例如总宽 360 mm 才能使用 `--square-mm 40`。不要直接使用印刷版的 20 mm。之后不能改变窗口大小、缩放比例或显示器。屏幕应为平面；避免反光、过曝和条纹。RGB 可以识别屏幕棋盘，但屏幕的深度读数可能无效或有偏差，深度验证不合格时换哑光实体标靶。

## 采集与求解

以下命令从项目根目录运行，40 必须换成实际测得格长：

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/calibrate.py capture --square-mm 40 --seconds 45
& '.\.venv-realsense\Scripts\python.exe' camera_lab/calibrate.py solve 'camera_lab/calibration/sessions/实际目录'
```

采集期间缓慢改变相机相对屏幕的距离和方向，在不同位置停稳，覆盖左/中/右、上/中/下、前后及不同倾角；保持所有内角点可见。至少接受 15 个不同视角，最多 30 个。采集有时间上限、结束释放相机；只保存本地。每接受一帧在终端计数，corners_*.png 可检查检测结果。未拍到标靶时保存 last_frame.png 和 NEEDS_MORE_VIEWS 状态，不生成假标定。

每 5 个视角保留 1 个，不参与内参拟合；固定内参后分别估计保留视角的标靶姿态并计算误差。候选要求保留视角 RMS <1 px、倾角跨度 >20°、角点跨度覆盖图像横纵各 >50%，这些是工程筛选阈值，不是精度保证。输出 camera_candidate.json，包括每视角误差和基于 RGB 平面的深度残差。量尺误差、屏幕平整度、角点分辨率仍影响结果；小重投影误差不证明绝对距离正确。候选不会自动替换现有相机参数。

## IMU 六姿态

相机坐标：从相机自身看，X 向右、Y 向下、Z 朝镜头前方。`x+` 表示把相机正 X 轴朝向天花板（静止比力为正 X）；`x-` 表示正 X 轴朝地面。Y/Z 类推。请支撑稳固，不要拉扯线缆；每次保持静止。

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/probe_imu.py --seconds 5
& '.\.venv-realsense\Scripts\python.exe' camera_lab/calibrate.py imu-add 'camera_lab/imu/刚生成的目录' --pose 'x+'
```

依次记录 x+、x-、y+、y-、z+、z-。工具检查设备序列号、时间戳域、样本数、静止噪声及方向；不接受一个姿态重复冒充六个姿态。已有姿态不覆盖。收齐后：

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/calibrate.py imu-solve
```

产生作用于 SDK 输出的加速度对角尺度/偏置、陀螺静止偏置候选。需要额外姿态与受控旋转验证；不估计陀螺尺度、交叉轴、动态时间偏移和完整视觉惯性外参，不写设备 NVRAM，不确定绝对航向。当前编码也尚未应用 IMU 姿态补偿。

## 重跑代码测试

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/calibrate.py target
& '.\.venv-realsense\Scripts\python.exe' camera_lab/test_calibration.py
```

使用当前独立环境中的 OpenCV 5.0.0.93、NumPy 2.3.5、pyrealsense2 2.58.4.10922、Pillow。板是 9×7 方格、8×6 内角点。参考 OpenCV 相机标定教程及 RealSense rs-imu-calibration；真实果蝇角度映射仍需要独立生物学依据。
