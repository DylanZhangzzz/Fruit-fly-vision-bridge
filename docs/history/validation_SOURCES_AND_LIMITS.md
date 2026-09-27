> Historical laboratory notes, preserved for context. Commands and relative paths below describe earlier local runs, not the release quickstart. Use [current installation](../installation.md) and [findings](../findings.md).

# 来源与未验证项

- 输入视柱：[Reiser lab 源表](https://github.com/reiserlab/male-drosophila-visual-system-connectome-code/blob/dbafc73124b5c96e96429cdf2a89d067cae841bc/results/exchange/ME_assigned_columns.csv)。本地 SHA-256 为 649140bab99503d13136e7cbe60372d981e728505d5c8db0b82f0ef33cfd8c8a。893 个右眼 L2 全部匹配，43130 和 56150 在该表中都为 (25,10)。这是来源中的重复，无法凭本实验判断解剖学原因；保留两者与歧义。
- [坐标说明](https://github.com/reiserlab/male-drosophila-visual-system-connectome-code/blob/main/docs/coordinate-systems.md) 定义了 hex 网格和参考方向，没有提供当前相机到每个 L2 的角度标定。归一化网格到图像是本项目假设。
- [眼睛结构研究](https://www.nature.com/articles/s41586-025-09276-5)及其 [eyemap_T4 原始代码](https://github.com/reiserlab/eyemap_T4) 提供微 CT / 神经结构视野研究方法。未建立该数据与本项目 MaleCNS L2 ID 的可靠角度对应；不能直接用另一标本的行号替换本项目映射。
- 模型来自本地 Xenova/fruit-fly-simulation，使用完整 MaleCNS 图和原 BrainCPU 简化动力学；不是原始 Shiu Brian2 后端。连接块按上游 manifest 校验，模型代码 SHA 记录于 network_summary.json。

## 结论边界

输入采样、网络单点地址和几何一致性分层验证。独立几何面积公式覆盖全部局部刺激响应；网络测试使用 120 Hz 而非局部暗点约 6.39 Hz，二者不等同于逐神经元端到端生物视觉响应验证。

891 个独立位置通过，2 个共享位置无法区分。893 个网络地址通过断连对照；887 个在指定条件下传播，6 个未观察到传播。不得把这 6 个判为死神经元，或把输入位置通过当作神经网络距离解码成功。

没有独立相机标定板、已知距离靶标、真实复眼朝向/视角标定，也没有验证 L2 亮度响应、连续动态视觉或物体识别。透明瓶身非零深度也可能错误。图像与深度帧时间差约 9.44 ms。所有生物位置标定为 UNVERIFIED。

下一步需要测量相机几何误差，并取得与当前 MaleCNS 视柱对应的视野角度/朝向依据，再重建映射和做时序视觉刺激实验。
