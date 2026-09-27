> Historical laboratory notes, preserved for context. Commands and relative paths below describe earlier local runs, not the release quickstart. Use [current installation](../installation.md) and [findings](../findings.md).

# 刺激图验证与 IMU 标定边界

## 已可执行

从项目根目录运行：

```powershell
& '.\.venv-realsense\Scripts\python.exe' camera_lab/generate_stimuli.py --validate
& '.\.venv-realsense\Scripts\python.exe' camera_lab/probe_imu.py --seconds 5
```

第一个命令生成 893 张 640×480 白底 3×3 黑点 PNG、白/黑控制图、总览和 manifest。验证从磁盘读取每张 PNG，以合成 1 m 有效深度送入生产采样器。results.csv 和 response.npy 保存逐项结果。它检查图像到输入通道，不是经真实相机拍摄的标定；不要把合成 1 m 深度当作测量。全部点总览只用于查看，不能代替单点实验。

第二个命令预热 2 秒再短时记录 IMU；通过 SDK 的流外参把加速度向量转到彩色相机坐标。向量只旋转，不加平移。加速度单位 m/s²，角速度 rad/s。静止时重力方向为比力反向；运动时不可这样解释。脚本记录时间戳域，域不一致不能直接积分时间差；不写设备 NVRAM。一次姿态不能估计完整偏置与尺度，SDK 返回单位阵/零参数也不能证明校准有效。

## 需要分开完成的三种标定

1. **相机几何**：具有已知物理尺寸的棋盘或 ChArUco 标靶，多位置、多倾角；用未参与拟合的视角评估重投影误差，用已知距离的非透明平面评估深度误差。显示屏上的像素须通过屏幕物理尺寸/姿态转换，不能直接当作相机像素。
2. **惯性参考**：静止多姿态估计加速度计偏置/尺度，静止段估计陀螺偏置，再用受控旋转与视觉参考验证。重力可约束俯仰和横滚；绝对航向须由标靶或其他外部参考确定，陀螺积分会漂移。运动融合还需要核对时间同步、传感器外参和陀螺坐标转换。
3. **果蝇视野**：取得与当前 MaleCNS 视柱可对应的真实视线方向、头部坐标定义或独立实验响应。现有 hex 网格归一化只是假设；IMU 不知道神经元对应的视角，无法补出这份缺失信息。不能用同一假设生成刺激、再成功命中，就证明假设真实。

## 官方参考

- https://github.com/realsenseai/librealsense/blob/master/doc/d435i.md
- https://github.com/realsenseai/librealsense/blob/master/examples/motion/rs-motion.cpp
- https://github.com/realsenseai/librealsense/tree/master/tools/rs-imu-calibration

官方示例也明确加速度不能确定绕重力轴的初始角度。标定工具可以写设备参数；当前项目只采集诊断，没有调用写入流程。
