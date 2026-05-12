# ToF Camera Sensor 方案评审文档

**日期**: 2026-05-09  
**模块**: CARLA Sensor / Python API / DFS Proto  
**Planning ID**: `tof`  
**面向对象**: 产品、测试、仿真平台、客户端集成同事  
**当前状态**: 第一版代码已在 `feature/tof` 实现并推送，完整 Editor 编译、运行时 smoke、DFS/proto 消费端验证仍需闭环确认。

---

## 1. Executive Summary

本方案新增一个 CARLA ToF 传感器：`sensor.camera.tof`。它在一个 sensor actor 内基于深度渲染结果生成 ToF 面阵点云，并在 Python callback 中一次返回：

- `point_cloud`: 传感器局部坐标系下的面阵点云，格式为 `xyzi32f`。

第一版只承诺输出点云，不输出 IR 图和 Gray 图。但数据模型会保留可扩展方向，后续可以在 ToF 传感器下继续补充：

- `ir`: `uint8 240x156`。
- `gray`: `uint16 240x156`。
- `point_cloud`: `uint8 240x156x16`，每个点为 `float32 x/y/z/i`。

对产品和测试来说，最关键的结论是：

- 新能力是一个新的 blueprint id：`sensor.camera.tof`，不会替换现有 `sensor.camera.depth`、`sensor.lidar.*` 或 RGB-D 传感器。
- 第一版 Python callback 类型是新增的 `carla.ToFMeasurement`，不复用 `carla.Image` 或 `carla.LidarMeasurement`。
- DFS/proto 新增 `oasis::ToFCamera`，不复用 LiDAR 或 RGB-D message。
- 默认分辨率为 `240x156`，默认点数为 `37440`。
- 点云 payload 固定大小为 `599040` bytes，即 `240 * 156 * 16`。
- 点云单位为毫米，坐标系为传感器局部右手系：`X` 向右、`Y` 向下、`Z` 向前。
- 点云强度 `i` 第一版固定为 `0.0f`，不代表真实反射强度。
- 深度值还原逻辑与 RGB-D 的 `uint16_mm` 深度编码保持一致，公共实现为 `DepthImageEncoding::ConvertEncodedDepthToUint16Millimeters()`。
- 当前实现还需要完成编译、运行时采样、PLY 检查和 DFS 消费端解析验收。

---

## 2. 背景与问题

当前 CARLA 已有普通 Depth camera、LiDAR、Stereo camera 和 RGB-D 复合传感器。现有能力能提供深度图或扫描式点云，但如果用户希望模拟一个 ToF 面阵传感器，会遇到几个问题：

- Depth camera 输出是图像，不是 ToF 产品侧期望的点云 payload。
- LiDAR 输出是扫描式点云，数据组织和 ToF 面阵相机不同。
- RGB-D 传感器关注 RGB + Depth 复合采集，不表达 ToF 的 IR、Gray、面阵点云扩展语义。
- 客户端和 DFS 数据流中缺少明确的 ToF 数据类型。
- 测试侧无法基于固定分辨率和固定 payload size 做稳定验收。

本方案把 ToF 作为新的 camera-family sensor，而不是改造 Depth camera 或 LiDAR。原因是 ToF 的业务语义是“面阵深度传感器”，第一版虽然只输出点云，但后续仍需要承载 IR、Gray、Laser/Dual-IR 等 ToF 相关设计。

| 对比项 | Depth Camera | LiDAR | ToF |
|---|---|---|---|
| 主要用途 | 深度图像显示或转换 | 扫描式三维点云 | 面阵 ToF 深度/点云采集 |
| 第一版输出 | `carla.Image` | `carla.LidarMeasurement` | `carla.ToFMeasurement` |
| 数据组织 | 2D image | point list | 2D grid point cloud |
| 默认分辨率 | camera attribute | lidar beams/config | `240x156` |
| 坐标系 | 图像语义 | LiDAR 局部坐标 | ToF 传感器局部光学坐标 |
| DFS message | camera image path | LiDAR path | `oasis::ToFCamera` |

---

## 3. 方案范围

### 3.1 本次包含

第一版 `sensor.camera.tof` 包含以下能力：

- 新增 Unreal sensor class：`AToFCameraSensor`。
- 新增 blueprint id：`sensor.camera.tof`。
- 默认分辨率为 `240x156`。
- 支持通过 `image_size_x` / `image_size_y` 配置 ToF 面阵尺寸。
- 支持 `fov`、`sensor_tick` 等 camera-family 通用配置。
- 支持 `min_distance` / `max_distance`，默认分别为 `0.3m` 和 `10.0m`。
- 支持 `depth_format` / `depth_output_format`，第一版使用 `uint16_mm`。
- 支持 `point_cloud_format`，第一版固定为 `xyzi32f`。
- 支持 `output_components`，第一版固定为 `point_cloud`。
- 深度还原复用 RGB-D 共享的 `DepthImageEncoding` 逻辑。
- 点云输出为固定 payload size，不因为无效点而改变长度。
- Python API 新增 `carla.ToFMeasurement` 和 `carla.ToFDetection`。
- DFS/proto 新增 `oasis::ToFCamera`。
- `PythonAPI/examples/manual_control.py` 增加 ToF 示例入口、ToF 深度视图和 PLY 保存能力。

### 3.2 本次不包含

以下内容不在第一版范围内：

- 不输出 IR 图像。
- 不输出 Gray 图像。
- 不模拟真实 ToF 相位测距、调制频率、曝光、噪声、多径、运动伪影等物理细节。
- 不模拟真实双 IR 或激光器能量分布。
- 不提供真实反射强度或置信度，`i` 固定为 `0.0f`。
- 不输出世界坐标系点云。
- 不把无效点从 payload 中删除。
- 不复用 `carla.LidarMeasurement`。
- 不复用 `carla.Image` 作为 Python callback 类型。
- 不复用 RGB-D message 或 LiDAR message。
- 不承诺第一版性能优化指标，第一版目标是功能闭环和数据契约正确。

---

## 4. 用户可见行为

### 4.1 Blueprint

新增 blueprint id：

```text
sensor.camera.tof
```

该 blueprint 是新增项，不改变现有传感器：

- `sensor.camera.rgb`
- `sensor.camera.depth`
- `sensor.camera.rgbd`
- `sensor.camera.stereo`
- `sensor.lidar.ray_cast`
- `sensor.lidar.ray_cast_semantic`
- `sensor.lidar.sc_lidar`

### 4.2 Python 回调数据

Python callback 中收到的新类型是 `carla.ToFMeasurement`：

```python
def callback(data: carla.ToFMeasurement):
    points = np.frombuffer(data.raw_data, dtype=np.float32).reshape(-1, 4)
    xyz = points[:, :3]
    intensity = points[:, 3]
```

其中：

- `data.width` 默认是 `240`。
- `data.height` 默认是 `156`。
- `data.fov` 是 ToF camera 的水平 FOV。
- `data.point_cloud_format` 第一版为 `xyzi32f` 对应的枚举值。
- `data.raw_data` 是点云 payload，不包含 ToF serializer header。
- `len(data)` 等于 `width * height`。
- 迭代 `data` 时，每个元素是 `carla.ToFDetection`。
- `ToFDetection.point.x/y/z` 和 `ToFDetection.intensity` 都是 `float32` 语义。

默认情况下：

| 字段 | 默认值 |
|---|---|
| `width` | `240` |
| `height` | `156` |
| point count | `37440` |
| bytes per point | `16` |
| payload size | `599040` bytes |
| point format | `float32 x, float32 y, float32 z, float32 i` |
| unit | millimeter |
| coordinate frame | sensor-local right-handed optical frame |

### 4.3 DFS / Proto 数据

DFS/proto 路径新增 `oasis::ToFCamera`，不复用 `oasis::Lidar` 或 `oasis::RGBDCamera`。

该 message 表达：

- `timestamp`
- `id`
- `frame`
- `pose`
- `fov`
- `width`
- `height`
- `point_cloud_format`
- `point_cloud_data`

其中 `point_cloud_data` 与 Python `data.raw_data` 的点云内容一致，都是连续的 `xyzi32f` 点云 payload。DFS 外层 `SensorData` 仍负责承载平台时间、frame、elapsed seconds、sensor type、role name 等通用元数据。

### 4.4 典型配置

第一版通过 blueprint attributes 配置 ToF 传感器。以下为**全部可配置参数**。

| Attribute | 默认值 | 说明 |
|---|:---:|---|
| `image_size_x` | `240` | ToF 面阵宽度（pixels）。与 `image_size_y` 共同决定点云总数 |
| `image_size_y` | `156` | ToF 面阵高度（pixels）。与 `image_size_x` 共同决定点云总数 |
| `fov` | `90.0` | 水平 FOV（degrees） |
| `depth_format` | `uint16_mm` | 深度中间格式，第一版固定为 `uint16_mm`。可选值由 `DepthImageEncoding` 定义 |
| `depth_output_format` | `uint16_mm` | 深度输出语义，与 RGB-D 的 `uint16_mm` 保持一致 |
| `point_cloud_format` | `xyzi32f` | 点云格式，第一版固定。每个点 `float32 x,y,z,i` |
| `output_components` | `point_cloud` | 输出组件。第一版仅 `point_cloud`，后续可扩展 `ir` / `gray` |
| `min_distance` | `0.3` | 最近有效距离（meters）。小于此距离的深度值无效 |
| `max_distance` | `10.0` | 最远有效距离（meters）。大于此距离的深度值无效 |
| `sensor_tick` | `0.0` | sensor tick 间隔（seconds）。`0.0` 表示每帧都触发 |

> 测试同事注意：`image_size_x * image_size_y * 16` = payload size（bytes）。改变分辨率会直接改变 payload 大小，消费端必须按配置值解析，不能硬编码。

---

## 5. Architecture / Flow

ToF 是一个 camera-family actor。第一版内部基于 depth render target 读取深度编码，再转换为固定尺寸面阵点云。

```text
┌──────────────────────────────────────────────────────────┐
│                  AToFCameraSensor Actor                  │
│                                                          │
│  ┌──────────────────────┐                               │
│  │ Depth Capture        │                               │
│  │ - ToF resolution     │                               │
│  │ - ToF FOV            │                               │
│  │ - Depth material     │                               │
│  │ - Min/Max distance   │                               │
│  └──────────┬───────────┘                               │
│             │                                           │
│             ▼                                           │
│  ┌──────────────────────┐                               │
│  │ Depth RenderTarget   │                               │
│  │ Encoded RGB depth    │                               │
│  └──────────┬───────────┘                               │
│             │                                           │
│             ▼                                           │
│  ┌──────────────────────┐                               │
│  │ DepthImageEncoding   │                               │
│  │ uint16_mm depth      │                               │
│  └──────────┬───────────┘                               │
│             │                                           │
│             ▼                                           │
│  ┌──────────────────────┐                               │
│  │ PointCloud Builder   │                               │
│  │ xyzi32f payload      │                               │
│  └──────────┬───────────┘                               │
└─────────────┼────────────────────────────────────────────┘
              ▼
┌──────────────────────────────────────────────────────────┐
│                  Client / DFS Output                     │
│  ├─ Python API: carla.ToFMeasurement                     │
│  └─ DFS Proto: oasis::ToFCamera                          │
└──────────────────────────────────────────────────────────┘
```

发送流程如下：

```text
┌──────────────────────┐
│ Sensor Tick          │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ PostPhysTick         │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Read FColor Pixels   │
│ Encoded RGB depth    │
└──────────┬───────────┘
           ▼
┌──────────────────────────────────────────────────────────┐
│ Convert Depth                                            │
│  ├─ Decode RGB depth                                     │
│  └─ Convert to uint16 millimeters                        │
└──────────┬───────────────────────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────┐
│ Build Point Cloud                                        │
│  ├─ Pixel grid to camera ray                             │
│  ├─ Depth in millimeters                                 │
│  └─ Output x/y/z/i float32                               │
└──────────┬───────────────────────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────┐
│ Outputs                                                  │
│  ├─ Python stream                                        │
│  └─ DFS/proto stream                                     │
└──────────────────────────────────────────────────────────┘
```

关键实现规则：

- 点云按图像行优先顺序组织，index 为 `v * width + u`。
- 每个像素固定生成一个点，因此 payload size 固定。
- 无效点写为 `(0, 0, 0, 0)`，不从 payload 中删除。
- Python 和 DFS 输出的 `x/y/z` 都是毫米。
- Python 和 DFS 输出的点云坐标都属于传感器局部坐标系。

---

## 6. Core Logic

### 6.1 Depth 链路

ToF 第一版的深度链路复用 camera depth material：

- 使用 depth postprocess material 生成编码深度图。
- Linux 下使用 `DepthEffectMaterial_GLSL_V2.DepthEffectMaterial_GLSL_V2`。
- `min_distance` / `max_distance` 语义与 Depth camera 保持一致，配置单位是 meter，内部 shader 参数使用 centimeter。
- 深度还原调用 `DepthImageEncoding::ConvertEncodedDepthToUint16Millimeters()`。

深度还原公式与 RGB-D 的 `uint16_mm` 逻辑保持一致：

```text
EncodedDepth = R + G * 256 + B * 256 * 256
NormalizedDepth = EncodedDepth / (256 * 256 * 256 - 1)
DepthMeters = NormalizedDepth * (MaxDistanceMeters - MinDistanceMeters) + MinDistanceMeters
DepthMillimeters = round(DepthMeters * 1000)
DepthUint16 = clamp(DepthMillimeters, 0, 65535)
```

这意味着测试时应重点验证 ToF 与 RGB-D 共用的 `uint16_mm` 深度还原逻辑是否一致，而不是为 ToF 单独定义一套深度编码规则。

### 6.2 Point Cloud 链路

ToF 点云由 `uint16_mm` 深度图反投影得到。对每个像素 `(u, v)`：

```text
FocalLength = Width / (2 * tan(FOV / 2))
CenterX = (Width - 1) / 2
CenterY = (Height - 1) / 2
Z = DepthMillimeters
X = (u - CenterX) * Z / FocalLength
Y = (v - CenterY) * Z / FocalLength
I = 0.0
```

输出坐标定义为传感器局部右手系：

| 轴 | 方向 | 单位 |
|---|---|---|
| `X` | right | millimeter |
| `Y` | down | millimeter |
| `Z` | forward | millimeter |
| `I` | intensity placeholder | float32, 第一版固定为 `0.0` |

### 6.3 Fixed Payload / Invalid Point

第一版保持固定数据包大小。无论场景里有多少有效深度点，payload 都始终包含 `width * height` 个点。

无效点规则：

- 读不到像素时，输出 `(0, 0, 0, 0)`。
- 深度值小于等于 `0` 时，输出 `(0, 0, 0, 0)`。
- 不删除无效点。
- 不改变点云 index。

默认配置下：

```text
Width = 240
Height = 156
PointCount = 240 * 156 = 37440
BytesPerPoint = 4 * sizeof(float32) = 16
PayloadSize = 37440 * 16 = 599040 bytes
```

测试和消费端应按固定 `width * height * 16` 解析，不应把点云当作可变长度有效点列表。

### 6.4 Frame / Timestamp

ToF 是单 actor、单 sensor stream：

- Python callback 的 `frame` 来自同一次 sensor tick。
- DFS `oasis::ToFCamera.frame` 与外层 `SensorData.frame` 应一致。
- `timestamp` / `elapsed_seconds` 语义沿用现有 CARLA sensor 数据流。
- 点云数据、width、height、fov 属于同一帧。

测试时应验证“单帧固定 payload 返回”，不应把“连续帧点云完全相同”作为正常预期。相机朝向或场景变化时，`Z` 和 `X/Y` 应随真实场景深度变化。

### 6.5 PLY 保存与可视化

`manual_control.py` 为 ToF 增加了两类测试辅助能力：

- ToF depth view：按 `Z` 深度着色，便于观察场景形状。
- PLY 保存：保存传感器局部坐标系下的 ASCII PLY 点云。

PLY 保存规则：

- 保存 `x y z intensity`。
- 坐标单位仍为毫米。
- 坐标系仍为 ToF 传感器局部坐标系。
- 不做 world transform。
- 保存时会过滤 `z <= 0` 的无效点。

LiDAR 的 view mode 只影响屏幕可视化，不改变 ToF PLY 文件的数据坐标系和单位。

---

## 7. Protocol And Data Model

### 7.1 Python API

Python API 新增类型：

| 类型 | 属性 / 方法 | 说明 |
|---|---|---|
| `carla.ToFMeasurement` | `width` | ToF 面阵宽度 |
| `carla.ToFMeasurement` | `height` | ToF 面阵高度 |
| `carla.ToFMeasurement` | `fov` | ToF 水平 FOV |
| `carla.ToFMeasurement` | `point_cloud_format` | 点云格式枚举，第一版为 `xyzi32f` |
| `carla.ToFMeasurement` | `raw_data` | 连续点云 payload，不包含 serializer header |
| `carla.ToFMeasurement` | `save_to_disk(path)` | 保存 PLY 点云 |
| `carla.ToFMeasurement` | `__len__()` | 点数，等于 `width * height` |
| `carla.ToFMeasurement` | iterator / index | 访问 `carla.ToFDetection` |
| `carla.ToFDetection` | `point` | `carla.Location`，承载 x/y/z |
| `carla.ToFDetection` | `intensity` | 强度字段，第一版固定为 `0.0` |

用户不需要手动跳过 ToF serializer header。Python `raw_data` 暴露的是点云数组本体，可以直接按 `float32` reshape。

### 7.2 DFS / Proto

DFS/proto 路径新增：

```text
oasis::ToFCamera
```

字段如下：

| 字段 | 说明 |
|---|---|
| `timestamp` | ToF message timestamp |
| `id` | sensor id |
| `frame` | sensor frame |
| `pose` | sensor pose，位置单位为 meter |
| `fov` | ToF camera FOV |
| `width` | ToF 面阵宽度 |
| `height` | ToF 面阵高度 |
| `point_cloud_format` | 第一版为 `xyzi32f` |
| `point_cloud_data` | 连续点云 payload |

需要注意两个单位：

- `pose.position` 沿用 DFS 现有传感器 pose 约定，单位为 meter。
- `point_cloud_data` 内的 `x/y/z` 是 ToF 点云数据，单位为 millimeter。

修改 `sensor_data.proto` 后，必须同步生成并提交：

- `LibCarla/source/carla/subscribe/proto/sensor_data.pb.h`
- `LibCarla/source/carla/subscribe/proto/sensor_data.pb.cc`

### 7.3 Output Extension Model

第一版只发送 `point_cloud`。后续扩展 IR / Gray 时，建议保持同一个 ToF sensor 和同一个 `oasis::ToFCamera` 语义，不新增另一个 ToF actor。

建议扩展目标如下：

| 输出 | 数据大小 | 语义 |
|---|---:|---|
| `ir` | `uint8 240x156` | IR intensity image |
| `gray` | `uint16 240x156` | Gray / depth-like image |
| `point_cloud` | `uint8 240x156x16` | `float32 x/y/z/i` point cloud |

第一版 `output_components=point_cloud` 的限制应在产品文档和测试用例中明确，避免误认为已经实现 IR/Gray 输出。

---

## 8. Product Review Points

产品评审建议重点确认以下问题：

- `sensor.camera.tof` 是否满足“新增 ToF 面阵传感器”的产品定义。
- 是否接受第一版只输出 `point_cloud`，IR/Gray 放入后续版本。
- 是否接受第一版 ToF 点云来自 depth render target，而不是完整物理 ToF 仿真。
- 是否接受默认分辨率固定为 `240x156`。
- 是否接受点云 payload 固定为 `599040` bytes。
- 是否接受点云单位为毫米。
- 是否接受点云坐标系为传感器局部右手系：`X right, Y down, Z forward`。
- 是否接受强度 `i` 第一版固定为 `0.0f`。
- 是否接受 Python callback 新增 `carla.ToFMeasurement`，不复用 `carla.LidarMeasurement`。
- 是否接受 DFS/proto 新增 `oasis::ToFCamera`，不复用 LiDAR 或 RGB-D message。
- 是否需要在用户文档中明确 pose 单位和 point cloud 单位不同。
- 是否需要后续版本加入真实 IR/Gray、强度、confidence、noise、laser/dual-IR 参数。

建议评审结论：

- 如果产品目标是“第一版可交付的 ToF 点云数据流”，当前方案匹配。
- 如果产品目标是“完整物理 ToF 相机仿真”，当前第一版不满足，需要另立物理 ToF 模型需求。
- 如果产品目标是“算法直接使用的固定面阵点云”，当前方案需要重点完成 runtime 和 DFS 验收。

---

## 9. Test Review Points

测试评审建议把验收拆成五层。

### 9.1 编译与注册

| 用例 | 预期 |
|---|---|
| Editor 编译 | 编译通过，无 C++/UHT/proto 相关错误 |
| PythonAPI 安装 | 当前 Python 环境加载的是新构建的 `carla` module |
| Blueprint 查询 | 能找到 `sensor.camera.tof` |
| Spawn sensor | `world.spawn_actor()` 成功 |
| 普通 sensor 回归 | `sensor.camera.depth`、`sensor.camera.rgbd`、LiDAR 不受影响 |

### 9.2 Python API

| 用例 | 预期 |
|---|---|
| callback 类型 | 收到 `carla.ToFMeasurement` |
| 基本属性 | `width=240`、`height=156`、存在 `fov` 和 `point_cloud_format` |
| 点数 | `len(data) == width * height` |
| raw size | `len(data.raw_data) == width * height * 16` |
| numpy 解析 | `np.frombuffer(data.raw_data, dtype=np.float32).reshape(-1, 4)` 成功 |
| 坐标单位 | `x/y/z` 为毫米级数值 |
| 强度字段 | `i` 第一版为 `0.0` |
| 无效点 | 无效点为 `(0, 0, 0, 0)` |
| save_to_disk | 可以保存 ASCII PLY 文件 |

### 9.3 Runtime 画面与点云

| 用例 | 预期 |
|---|---|
| ToF depth view | `manual_control.py` 可显示按深度着色的 ToF 视图 |
| 点云视图 | 可看到随场景变化的点云形状 |
| 靠近/远离物体 | `Z` 值随距离变化 |
| 改变 FOV | 点云横向/纵向展开变化符合 FOV |
| 改变分辨率 | payload size 按 `width * height * 16` 变化 |
| PLY 打开 | CloudCompare 等工具可按 `x/y/z` 打开点云 |
| PLY 坐标 | PLY 仍为传感器局部坐标系，不是世界坐标系 |

### 9.4 DFS / Proto

| 用例 | 预期 |
|---|---|
| message 类型 | 消费端能识别 `oasis::ToFCamera` |
| 基本字段 | `width`、`height`、`fov`、`frame` 正确 |
| payload 字段 | `point_cloud_data.size() == width * height * 16` |
| format 字段 | `point_cloud_format == "xyzi32f"` |
| pose 字段 | `pose.position` 单位为 meter |
| 点云数据 | `point_cloud_data` 内 `x/y/z` 单位为 millimeter |
| 与 LiDAR 区分 | ToF 不被解析成 LiDAR message |

### 9.5 数据一致性

| 用例 | 预期 |
|---|---|
| Python vs DFS size | 同配置下两端 point cloud payload size 一致 |
| Python vs DFS format | 两端都按 `float32 x/y/z/i` 解析 |
| Python vs DFS 坐标系 | 两端都是传感器局部右手系 |
| Python vs DFS 单位 | 两端 `x/y/z` 都是 millimeter |
| RGB-D 共享深度逻辑 | ToF 深度还原与 RGB-D `uint16_mm` 使用同一公共逻辑 |

---

## 10. Acceptance Criteria

第一版建议满足以下条件后，才进入“功能可验收”状态：

- Editor 编译通过。
- PythonAPI 能识别 `carla.ToFMeasurement`。
- 可以 spawn `sensor.camera.tof`。
- 默认配置下 callback 中 `width=240`、`height=156`。
- 默认配置下 `len(data) == 37440`。
- 默认配置下 `len(data.raw_data) == 599040`。
- `data.raw_data` 可以按 `float32 x/y/z/i` 解析。
- 点云 `x/y/z` 单位为毫米。
- 点云坐标系为传感器局部右手系：`X right, Y down, Z forward`。
- 无效点保持 `(0, 0, 0, 0)`，不改变 payload size。
- ToF depth view 可以观察到场景深度形状。
- PLY 保存结果可用外部点云工具打开。
- DFS/proto 消费端可以收到并解析 `oasis::ToFCamera`。
- Python 与 DFS 的点云 payload 格式、单位、坐标系保持一致。
- 普通 Depth、RGB-D、LiDAR 传感器不发生回归。

---

## 11. Risks And Mitigations

| 风险 | 影响 | 应对 |
|---|---|---|
| PythonAPI 与 Editor 构建版本不一致 | import 或 callback 类型失败 | 编译后重新安装 PythonAPI，并确认加载的是当前 `.so` |
| depth material 或 readback 参数错误 | 点云 `Z` 不随场景变化 | 对比 ToF depth view、PLY 和场景距离，重点检查 depth decode 链路 |
| ToF 与 RGB-D 深度还原逻辑分叉 | 两类传感器数据格式不一致 | 强制复用 `DepthImageEncoding::ConvertEncodedDepthToUint16Millimeters()` |
| 消费端误把点云当 meter | 下游尺度错误 | 文档、proto 消费说明和测试用例明确 `point_cloud_data` 内 `x/y/z` 为 millimeter |
| 消费端误把 ToF 点云当 world frame | 下游位姿叠加错误 | 文档明确点云为 sensor-local frame，world transform 由消费端按 pose 自行处理 |
| 无效点被错误删除 | payload size 不稳定 | 保持 `(0,0,0,0)` 占位，测试固定 payload size |
| 强度字段被当真实反射强度 | 产品语义误解 | 第一版明确 `i=0.0f`，真实 intensity 后续单独设计 |
| CloudCompare scalar 显示误操作 | 用户无法按 Z 着色 | 打开 PLY 时 `x/y/z` 只映射坐标；如需 scalar，后续另加独立 scalar 字段 |
| proto 生成文件漏提交 | C++ 编译找不到 `oasis::ToFCamera` | `.proto` 修改后必须提交 `.pb.h/.pb.cc` |
| 第一版范围被误认为包含 IR/Gray | 验收标准偏离 | 明确第一版只验收 `point_cloud`，IR/Gray 放入后续版本 |

---

## 12. Code Navigation

| 文件 | 职责 |
|---|---|
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/ToFCameraSensor.h` | ToF Unreal sensor class 声明、默认尺寸、payload size、attribute 访问 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/ToFCameraSensor.cpp` | ToF actor、blueprint definition、depth readback、point cloud 构造逻辑 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/DepthImageEncoding.h` | RGB-D / ToF 共享深度编码接口声明 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/DepthImageEncoding.cpp` | encoded RGB depth 到 `uint16_mm` 的公共转换实现 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/Sensor.h` | `SendDataToClient()` ToF 分支和 DFS message 入口声明 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/Sensor.cpp` | `HandleToFMessage()` 实现，填充 `oasis::ToFCamera` |
| `LibCarla/source/carla/sensor/data/ToFMeasurement.h` | 客户端 ToF 数据类型、`ToFDetection`、Python payload header offset |
| `LibCarla/source/carla/sensor/s11n/ToFCameraSerializer.h` | ToF serializer header、`xyzi32f` format id、序列化入口 |
| `LibCarla/source/carla/sensor/s11n/ToFCameraSerializer.cpp` | ToF serializer 编译单元 |
| `LibCarla/source/carla/sensor/SensorRegistry.h` | `sensor.camera.tof` serializer 注册 |
| `LibCarla/source/carla/subscribe/proto/sensor_data.proto` | `oasis::ToFCamera` 协议定义 |
| `LibCarla/source/carla/subscribe/proto/sensor_data.pb.h` | proto 生成头文件 |
| `LibCarla/source/carla/subscribe/proto/sensor_data.pb.cc` | proto 生成实现 |
| `PythonAPI/carla/src/SensorData.cpp` | Python binding，暴露 `carla.ToFMeasurement` 和 `carla.ToFDetection` |
| `PythonAPI/examples/manual_control.py` | ToF 示例入口、ToF depth view、ToF PLY 保存 |

---

## 13. Current Status And Next Steps

当前已完成：

- 第一版 ToF 代码已在 `feature/tof` 实现并推送。
- 已新增 `sensor.camera.tof` blueprint definition。
- 已新增 `carla.ToFMeasurement` Python callback 类型。
- 已新增 `oasis::ToFCamera` DFS/proto message。
- 已将默认分辨率调整为 `240x156`。
- 已将点云 payload 定义为 `xyzi32f`，默认大小 `599040` bytes。
- 已将 Python 和 DFS 点云 `x/y/z` 统一为毫米。
- 已将点云坐标系统一为传感器局部右手系。
- 已将深度还原切到 RGB-D 共享的 `uint16_mm` 公共逻辑。
- 已在 `manual_control.py` 增加 ToF 示例、深度视图和 PLY 保存。

当前未完成：

- 未完成最新代码的完整 Editor 编译确认。
- 未完成 PythonAPI 重新安装后的 import/callback smoke。
- 未完成 runtime spawn/listen smoke。
- 未完成 PLY 文件与真实场景形状的系统验收。
- 未完成 DFS/proto 消费端解析实测。
- 未完成普通 Depth、RGB-D、LiDAR 回归测试。

建议下一步：

1. 按 repo 规则由用户明确触发 Editor 编译，并使用 `build-editor` skill。
2. 编译失败时只修 build error，不扩大功能范围。
3. 编译通过后重新安装 PythonAPI，确认 `import carla` 加载的是当前构建版本。
4. 执行最小 runtime smoke：spawn `sensor.camera.tof`，监听 `carla.ToFMeasurement`。
5. 验证默认配置下 `width=240`、`height=156`、`raw_data=599040 bytes`。
6. 保存 PLY，确认点云为传感器局部坐标、单位毫米、`Z` 随场景深度变化。
7. 验证 DFS/proto 消费端能解析 `oasis::ToFCamera`。
8. 完成回归测试后，再决定是否进入产品验收或继续补 IR/Gray/Intensity 等二期能力。

---

## 14. Review Decision Checklist

评审会上建议直接确认以下结论：

- 是否同意 `sensor.camera.tof` 作为新增 blueprint id。
- 是否同意第一版只输出 `point_cloud`。
- 是否同意 IR 和 Gray 放入后续版本。
- 是否同意第一版点云格式为 `xyzi32f`。
- 是否同意默认分辨率为 `240x156`。
- 是否同意默认 payload size 为 `599040` bytes。
- 是否同意点云 `x/y/z` 单位为 millimeter。
- 是否同意点云坐标系为 sensor-local right-handed optical frame：`X right, Y down, Z forward`。
- 是否同意无效点用 `(0,0,0,0)` 占位，保持固定 payload size。
- 是否同意第一版 `i=0.0f`，不作为真实强度。
- 是否同意 Python callback 新增 `carla.ToFMeasurement`。
- 是否同意 DFS/proto 新增 `oasis::ToFCamera`。
- 是否同意 ToF 与 RGB-D 共享 `uint16_mm` 深度还原逻辑。
- 是否同意验收重点先放在 build、spawn、callback、payload size、PLY、DFS/proto 解析和现有 sensor 回归。
- 是否把 IR、Gray、真实 intensity、confidence、noise、多径、laser/dual-IR 参数放入后续版本。
