# RGB-D Camera Sensor 方案评审文档

**日期**: 2026-04-30  
**模块**: CARLA Sensor / Python API / DFS Proto  
**Planning ID**: `rgbd`  
**面向对象**: 产品、测试、仿真平台、客户端集成同事  
**当前状态**: 第一版代码已实现并进入编译修复阶段，完整 Editor 编译、运行时 smoke、DFS/proto 消费端验证仍未完成。

---

## 1. Executive Summary

本方案新增一个 CARLA 复合传感器：`sensor.camera.rgbd`。它在一个 sensor actor 内同时采集一张 RGB 图像和一张 Depth 图像，并在 Python callback 中一次返回：

- `rgb_image`: 普通 RGB camera 输出。
- `depth_image`: Depth camera 输出，编码逻辑严格沿用现有 `sensor.camera.depth`。

这个传感器的目标不是做“对齐后的 RGB-D 相机”，而是提供一个更方便的复合采集入口：RGB 和 Depth 共享同一个 actor 生命周期、同一个 sensor tick、同一个 frame/timestamp，但两路图像的分辨率、FOV 和相对安装位置可以完全独立。

对产品和测试来说，最关键的结论是：

- 新能力是一个新的 blueprint id：`sensor.camera.rgbd`，不会替换现有 `sensor.camera.rgb` 或 `sensor.camera.depth`。
- RGB 和 Depth 不要求分辨率一致，也不承诺像素级对齐。
- Depth 语义不重新定义，继续使用 CARLA 现有 depth camera 的颜色编码和 converter 使用方式。
- 第一版只承诺 RGB 为 `RGBA`，暂不扩展 YUV 等格式。
- 当前实现还没有完成完整编译和运行时验收，评审通过后下一步应优先做 build/runtime 闭环，而不是继续扩功能。

---

## 2. 背景与问题

当前 CARLA 已有普通 RGB camera、Depth camera 和 Stereo camera。现有能力能单独采集 RGB 或 Depth，但如果用户希望在同一个仿真场景里把 RGB 与 Depth 作为一个逻辑传感器使用，会遇到几个问题：

- 需要自己创建两个 actor，并手动管理两者的生命周期。
- 需要在客户端自行合并两路数据。
- 两路传感器的 frame/timestamp 对齐关系需要用户自己判断。
- Python 示例和数据流协议中没有一个明确的 RGB-D 复合数据类型。

本方案参考 stereo 的“一个 actor 内多路 capture component”组织方式，但不复用 stereo 的协议和同分辨率假设。原因是 RGB-D 和 stereo 的业务语义不同：

| 对比项 | Stereo | RGB-D |
|---|---|---|
| 主要用途 | 左右目相机、视差、深度辅助 | RGB + Depth 复合采集 |
| 分辨率关系 | 通常要求同尺寸或强相关 | 明确允许不同尺寸 |
| 子图语义 | left/right/depth/disparity | rgb/depth |
| 是否像素对齐 | stereo 语义更强 | 第一版不承诺 |
| 协议复用 | 不适用 | 必须新增 RGB-D 专用协议 |

---

## 3. 方案范围

### 3.1 本次包含

第一版 `sensor.camera.rgbd` 包含以下能力：

- 一个 Unreal actor 内部包含 RGB capture 和 Depth capture。
- RGB 和 Depth 支持独立分辨率。
- RGB 和 Depth 支持独立 FOV。
- RGB 和 Depth 支持独立 relative transform，包括 location 和 rotation。
- RGB 支持普通 RGB camera 的畸变和后处理能力。
- Depth 严格沿用 `ADepthCamera` 的 depth material、`min_distance`、`max_distance` 和 depth 编码逻辑。
- Python API 新增 `carla.RGBDImageData`，暴露 `rgb_image` 和 `depth_image`。
- DFS/proto 新增 `oasis::RGBDCamera`，不复用 stereo message。
- `PythonAPI/examples/manual_control.py` 增加 `sensor.camera.rgbd` 示例入口，并支持 RGB/Depth 显示切换。
- 默认开启 `ForceSensorFrameSync` 时，RGB-D 使用与普通 RGB/stereo 一致的 frame sync 调度逻辑。

### 3.2 本次不包含

以下内容不在第一版范围内：

- 不做 RGB 与 Depth 像素级对齐。
- 不做 depth 到 RGB 平面的重投影、裁剪或重采样。
- 不把 RGB-D 拆成两个独立 CARLA actor。
- 不重新定义 depth 数据格式，不改为 `uint16_mm` 或 `float32_m`。
- 不复用 `StereoImageData`、`StereoCameraSerializer` 或 stereo payload layout。
- 不支持 YUV RGB 输出格式，第一版 RGB 只做 `RGBA`。
- 不承诺性能优化指标，第一版目标是功能闭环和语义正确。

---

## 4. 用户可见行为

### 4.1 Blueprint

新增 blueprint id：

```text
sensor.camera.rgbd
```

该 blueprint 是新增项，不改变现有传感器：

- `sensor.camera.rgb`
- `sensor.camera.depth`
- `sensor.camera.semantic_segmentation`
- `sensor.camera.instance_segmentation`
- `sensor.camera.dvs`
- `sensor.camera.optical_flow`
- `sensor.camera.normals`
- `sensor.camera.stereo`

### 4.2 Python 回调数据

Python callback 中收到的新类型是 `carla.RGBDImageData`。只需通过两个属性获取数据：

```python
def callback(data: carla.RGBDImageData):
    rgb = data.rgb_image       # carla.Image, 和普通 RGB camera 的 callback 数据用法一致
    depth = data.depth_image   # carla.Image, 和普通 Depth camera 的 callback 数据用法一致
```

不需要手动切 payload。`rgb_image` 和 `depth_image` 都是标准 `carla.Image` 类型，可以直接用现有 converter（如 `cc.RGB`、`cc.Depth`）处理。

| 属性 | 类型 | 说明 |
|---|---|---|
| `data.rgb_image` | `carla.Image` | RGB 子图。等同于 `sensor.camera.rgb` 的 callback 数据 |
| `data.depth_image` | `carla.Image` | Depth 子图。等同于 `sensor.camera.depth` 的 callback 数据，沿用相同 depth converter |
| `data.rgb_image.width` / `.height` | `int` | 分别等于 `rgb_image_size_x` / `rgb_image_size_y` 配置值 |
| `data.depth_image.width` / `.height` | `int` | 分别等于 `depth_image_size_x` / `depth_image_size_y` 配置值 |
| `data.frame` | `int` | 同帧 frame number（两张子图一致） |
| `data.timestamp` | `float` | 同帧 timestamp（两张子图一致） |

### 4.3 典型配置

第一版通过 blueprint attributes 配置 RGB 和 Depth 子相机。

**RGB 子相机参数**：

| Attribute | 默认值 | 说明 |
|---|:---:|---|
| `rgb_image_size_x` | `800` | RGB 图像宽度（pixels） |
| `rgb_image_size_y` | `600` | RGB 图像高度（pixels） |
| `rgb_fov` | `90.0` | RGB 水平 FOV（degrees） |
| `rgb_image_type` | `RGBA` | RGB 像素格式，第一版仅支持 `RGBA` |
| `rgb_x` | `0.0` | RGB 子相机相对 actor 的 X 偏移（meters） |
| `rgb_y` | `0.0` | RGB 子相机相对 actor 的 Y 偏移（meters） |
| `rgb_z` | `0.0` | RGB 子相机相对 actor 的 Z 偏移（meters） |
| `rgb_pitch` | `0.0` | RGB 子相机相对 actor 的 pitch（degrees） |
| `rgb_yaw` | `0.0` | RGB 子相机相对 actor 的 yaw（degrees） |
| `rgb_roll` | `0.0` | RGB 子相机相对 actor 的 roll（degrees） |

**Depth 子相机参数**：

| Attribute | 默认值 | 说明 |
|---|:---:|---|
| `depth_image_size_x` | `800` | Depth 图像宽度（pixels） |
| `depth_image_size_y` | `600` | Depth 图像高度（pixels） |
| `depth_fov` | `90.0` | Depth 水平 FOV（degrees） |
| `min_distance` | `0.3` | Depth 最近有效距离（meters） |
| `max_distance` | `10.0` | Depth 最远有效距离（meters） |
| `depth_x` | `0.0` | Depth 子相机相对 actor 的 X 偏移（meters） |
| `depth_y` | `0.0` | Depth 子相机相对 actor 的 Y 偏移（meters） |
| `depth_z` | `0.0` | Depth 子相机相对 actor 的 Z 偏移（meters） |
| `depth_pitch` | `0.0` | Depth 子相机相对 actor 的 pitch（degrees） |
| `depth_yaw` | `0.0` | Depth 子相机相对 actor 的 yaw（degrees） |
| `depth_roll` | `0.0` | Depth 子相机相对 actor 的 roll（degrees） |

**共享参数**：

| Attribute | 默认值 | 说明 |
|---|:---:|---|
| `sensor_tick` | `0.0` | sensor tick 间隔（seconds），`0.0` 表示每帧都触发 |
| `image_type` | `RGBA` | RGB 输出像素格式，第一版固定为 `RGBA` |

> 测试同事注意：RGB 和 Depth 子相机参数完全独立。例如可以配置 `rgb_image_size_x=1920, rgb_image_size_y=1080` 同时 `depth_image_size_x=640, depth_image_size_y=480`。两边的尺寸/FOV/相对位置不要求一致。

---

## 5. Architecture / Flow

RGB-D 是一个 actor 内的双 capture 结构。RGB 和 Depth 有独立渲染目标，但由同一个 sensor tick 触发。

```text
┌──────────────────────────────────────────────────────────┐
│                 ARGBDCameraSensor Actor                  │
│                                                          │
│  ┌──────────────────────┐      ┌──────────────────────┐  │
│  │ RGB Capture          │      │ Depth Capture        │  │
│  │ - RGB resolution     │      │ - Depth resolution   │  │
│  │ - RGB FOV            │      │ - Depth FOV          │  │
│  │ - RGB transform      │      │ - Depth transform    │  │
│  │ - RGB postprocess    │      │ - Depth material     │  │
│  └──────────┬───────────┘      └──────────┬───────────┘  │
│             │                             │              │
│             ▼                             ▼              │
│  ┌──────────────────────┐      ┌──────────────────────┐  │
│  │ RGB RenderTarget     │      │ Depth RenderTarget   │  │
│  └──────────┬───────────┘      └──────────┬───────────┘  │
│             │                             │              │
│             └──────────────┬──────────────┘              │
│                            ▼                             │
│                 RGBD Payload Builder                     │
└────────────────────────────┬─────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────┐
│                 Client / DFS Output                      │
│  ├─ Python API: carla.RGBDImageData                      │
│  └─ DFS Proto: oasis::RGBDCamera                         │
└──────────────────────────────────────────────────────────┘
```

发送流程如下：

```text
┌──────────────────────┐
│ Sensor Tick          │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ CanSensorWork        │
│ ForceFrameSync aware │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ SensorWork           │
└──────────┬───────────┘
           ▼
┌──────────────────────────────────────────────────────────┐
│ CaptureScene                                             │
│  ├─ RGB CaptureScene                                     │
│  └─ Depth CaptureScene                                   │
└──────────┬───────────────────────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────┐
│ Render Thread Readback                                   │
│  ├─ RGB Readback                                         │
│  └─ Depth Readback                                       │
└──────────┬───────────────────────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────┐
│ RGBD Serialization                                       │
│  ├─ RGB header + RGB bytes                               │
│  └─ Depth header + Depth bytes                           │
└──────────┬───────────────────────────────────────────────┘
           ▼
┌──────────────────────────────────────────────────────────┐
│ Outputs                                                  │
│  ├─ Python stream                                        │
│  └─ DFS/proto stream                                     │
└──────────────────────────────────────────────────────────┘
```

关键实现规则：

- 必须先触发本帧 `CaptureScene()`，再处理 render-thread readback readiness。
- 不允许在 capture 之前用旧 readback 状态提前 return，否则可能导致整帧饿死。
- RGB 和 Depth 的 width/height/FOV/payload size 必须分别记录，不能用一个顶层尺寸拆包。

---

## 6. Core Logic

### 6.1 RGB 链路

RGB 链路继承普通 RGB camera 的语义：

- 使用 `AShaderBasedSensor` 作为基类。
- 复用基础 `CaptureComponent2D` / `CaptureRenderTarget`。
- 支持普通 RGB camera 的 distortion 和 postprocess attributes。
- 第一版 payload 使用 `RGBA`。

这意味着产品层面可以把 `rgb_image` 理解为“普通 RGB camera 的子图输出”，而不是新的图像模型。

### 6.2 Depth 链路

Depth 链路严格参考已有 `ADepthCamera`：

- 使用同款 depth postprocess material。
- Linux 下参考 `DepthEffectMaterial_GLSL_V2.DepthEffectMaterial_GLSL_V2`。
- `min_distance` / `max_distance` 语义沿用 `ADepthCamera`，内部按现有实现换算并写入 shader 参数。
- 输出仍为 `carla.Image`，不新增 `ImageUint16` 或其它 depth 数据类型。

这意味着测试时应拿 `sensor.camera.depth` 作为语义基线，验证 RGB-D 的 `depth_image` 是否符合现有 depth camera 的使用方式，而不是拿真实物理距离数组作为第一版验收目标。

### 6.3 Frame / Timestamp

RGB-D 的两张子图由同一个 actor 的同一个 sensor tick 触发：

- 顶层 frame 一致。
- 顶层 timestamp 一致。
- 不承诺两个子图逐像素对应。
- 不承诺 RGB 和 Depth 的内参一致。

测试时应验证“同帧复合返回”，不应把“像素对齐”作为失败条件。

### 6.4 ForceSensorFrameSync

当前 CARLA 默认开启 `ForceSensorFrameSync`。RGB-D 必须沿用普通 RGB/stereo 的调度逻辑：

- frame sync 关闭时，按 `IsReadyToTick()` 和 sensor update 需求判断。
- frame sync 开启时，按 world frame counter、world frame interval 和 sensor tick interval 判断是否产生新的 sensor frame。

该规则的目的是让 RGB-D 在同步仿真和固定 tick 场景中表现与现有 camera 传感器一致。

---

## 7. Protocol And Data Model

### 7.1 Python API

Python API 新增类型：

| 类型 | 属性 | 说明 |
|---|---|---|
| `carla.RGBDImageData` | `rgb_image` | RGB 子图，类型为 `carla.Image` |
| `carla.RGBDImageData` | `depth_image` | Depth 子图，类型为 `carla.Image` |

用户不需要手动切 payload。客户端反序列化时由 `RGBDCameraSerializer` 拆出两张子图。

### 7.2 DFS / Proto

DFS/proto 路径新增 `oasis::RGBDCamera`，不复用 `oasis::StereoCamera`。

该 message 需要分别表达：

- RGB width/height/FOV/pixel format/pose/bytes。
- Depth width/height/FOV/pixel format/pose/bytes。
- Depth `min_distance` / `max_distance`。
- 顶层 frame/timestamp/sensor metadata。

修改 `sensor_data.proto` 后，必须同步生成并提交：

- `LibCarla/source/carla/subscribe/proto/sensor_data.pb.h`
- `LibCarla/source/carla/subscribe/proto/sensor_data.pb.cc`

---

## 8. Product Review Points

产品评审建议重点确认以下问题：

- `sensor.camera.rgbd` 是否满足“一个逻辑传感器同时返回 RGB 和 Depth”的产品定义。
- 是否接受第一版不做像素级对齐，只保证同 tick/frame/timestamp。
- 是否接受第一版 RGB 只支持 `RGBA`。
- 是否接受 Depth 继续沿用 CARLA 现有 depth color encoding，而不是新增米制深度数组。
- 是否需要在用户文档中明确说明 RGB/Depth 可不同分辨率、不同 FOV、不同相对位置。
- 是否需要在 UI 或示例中把 RGB/Depth 显示切换作为默认示例能力。
- 是否需要在后续版本规划 aligned depth、calibration metadata、YUV、性能优化等增强项。

建议评审结论：

- 如果产品目标是“复合采集入口”和“简化客户端集成”，当前方案匹配。
- 如果产品目标是“算法直接使用的对齐 RGB-D 数据集”，当前第一版不满足，需要另立 aligned RGB-D 需求。

---

## 9. Test Review Points

测试评审建议把验收拆成四层。

### 9.1 编译与注册

| 用例 | 预期 |
|---|---|
| Editor 编译 | 编译通过，无 C++/UHT/proto 相关错误 |
| Blueprint 查询 | 能找到 `sensor.camera.rgbd` |
| Spawn sensor | `world.spawn_actor()` 成功 |
| 普通 camera 回归 | `sensor.camera.rgb` 和 `sensor.camera.depth` 不受影响 |

### 9.2 Python API

| 用例 | 预期 |
|---|---|
| callback 类型 | 收到 `carla.RGBDImageData` |
| 子图属性 | 存在 `rgb_image` 和 `depth_image` |
| 子图类型 | 两者都是 `carla.Image` |
| 不同分辨率 | RGB 和 Depth 的 width/height 分别等于配置值 |
| frame/timestamp | 两张子图属于同一次 RGB-D 回调 |
| depth converter | `depth_image` 可用 `cc.Depth` 显示或保存 |

### 9.3 Runtime 画面

| 用例 | 预期 |
|---|---|
| RGB 显示 | RGB 画面持续更新 |
| Depth 显示 | Depth 画面持续更新 |
| `manual_control.py` 切换 | 切到 RGB-D 后可在 RGB/Depth 模式间切换 |
| 切出再切回 | 不应保留上一种普通 RGB sensor 的旧画面 |
| 不同 FOV | RGB/Depth 视角差异符合配置 |
| 不同 transform | 改变 `depth_x/y/z/pitch/yaw/roll` 后 Depth 视角变化 |

### 9.4 DFS / Proto

| 用例 | 预期 |
|---|---|
| message 类型 | 消费端能识别 `oasis::RGBDCamera` |
| RGB 字段 | RGB 尺寸、FOV、pose、bytes 正确 |
| Depth 字段 | Depth 尺寸、FOV、pose、bytes 正确 |
| 距离字段 | `min_distance` / `max_distance` 正确传递 |
| 与 stereo 区分 | RGB-D 不被解析成 `oasis::StereoCamera` |

---

## 10. Acceptance Criteria

第一版建议满足以下条件后，才进入“功能可验收”状态：

- Editor 编译通过。
- PythonAPI 能识别 `carla.RGBDImageData`。
- 可以 spawn `sensor.camera.rgbd`。
- RGB 和 Depth 配置不同分辨率时，callback 中两张子图尺寸正确。
- RGB 和 Depth 两路画面都持续更新。
- `manual_control.py` 可以切换到 RGB-D 并显示 RGB/Depth。
- `depth_image` 的使用方式与现有 `sensor.camera.depth` 保持一致。
- DFS/proto 消费端可以收到并解析 `oasis::RGBDCamera`。
- 普通 `sensor.camera.rgb`、`sensor.camera.depth`、`sensor.camera.stereo` 不发生回归。

---

## 11. Risks And Mitigations

| 风险 | 影响 | 应对 |
|---|---|---|
| Depth material 被 RGB postprocess 链路影响 | Depth 输出语义错误 | 测试时对比 `sensor.camera.depth`，并重点检查 material/shader 参数 |
| readback 顺序错误 | RGB/Depth 不更新或保留旧画面 | 保持先 `CaptureScene()` 再 readback readiness 的规则 |
| serializer 仍隐含同分辨率假设 | 不同分辨率时拆包错误 | RGB-D header 必须分别记录子图尺寸和 payload size |
| proto 生成文件漏提交 | C++ 编译找不到 `oasis::RGBDCamera` | `.proto` 修改后必须提交 `.pb.h/.pb.cc` |
| PythonAPI 与 Editor 构建版本不一致 | callback 类型不可识别 | 编译和 smoke 时确认 Python API 安装/加载的是当前版本 |
| 产品误认为已做对齐 | 验收标准偏离第一版目标 | 在文档、示例和测试用例中明确“不承诺像素级对齐” |

---

## 12. Code Navigation

| 文件 | 职责 |
|---|---|
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/RGBDCameraSensor.h` | RGB-D Unreal sensor class 声明 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/RGBDCameraSensor.cpp` | RGB-D actor、capture、attribute、tick/send 逻辑 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/PixelReader.h` | RGB-D readback 入口声明 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/PixelReader.cpp` | RGB-D RGB/Depth render target readback 和 payload 构造 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/Sensor.h` | DFS/proto RGB-D message 入口声明 |
| `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/Sensor.cpp` | `HandleRGBDMessage()` 实现 |
| `LibCarla/source/carla/sensor/data/RGBDImageData.h` | 客户端 RGB-D 数据类型 |
| `LibCarla/source/carla/sensor/s11n/RGBDCameraSerializer.h` | Python stream RGB-D 反序列化 |
| `LibCarla/source/carla/sensor/SensorRegistry.h` | `sensor.camera.rgbd` serializer 注册 |
| `LibCarla/source/carla/subscribe/proto/sensor_data.proto` | `oasis::RGBDCamera` 协议定义 |
| `LibCarla/source/carla/subscribe/proto/sensor_data.pb.h` | proto 生成头文件 |
| `LibCarla/source/carla/subscribe/proto/sensor_data.pb.cc` | proto 生成实现 |
| `PythonAPI/carla/src/SensorData.cpp` | Python binding，暴露 `carla.RGBDImageData` |
| `PythonAPI/examples/manual_control.py` | RGB-D 示例使用入口和显示切换 |

---

## 13. Current Status And Next Steps

当前已完成：

- 方案设计文档已落在 `.planning/conversations/rgbd/`。
- 第一版 WIP 代码已实现并提交。
- 已修复已知的 `ImageTmpl` protected constructor 编译问题。
- 已修复 `uint32 UPROPERTY(BlueprintReadWrite)` 的 UHT 编译问题。
- 已在 `manual_control.py` 增加 RGB-D 示例入口。

当前未完成：

- 未完成最新代码的完整 Editor 编译确认。
- 未完成 runtime spawn/listen smoke。
- 未完成 Python callback payload 正确性实测。
- 未完成 DFS/proto 消费端解析实测。
- 未完成普通 RGB/Depth/Stereo 回归测试。

建议下一步：

1. 按 repo 规则由用户明确触发 Editor 编译，并使用 `build-editor` skill。
2. 编译失败时只修 build error，不扩大功能范围。
3. 编译通过后执行最小 runtime smoke：spawn `sensor.camera.rgbd`，配置 RGB/Depth 不同分辨率、FOV、transform。
4. 验证 Python callback 中 `rgb_image` 和 `depth_image` 都持续更新。
5. 验证 DFS/proto 消费端能解析 `oasis::RGBDCamera`。
6. 完成回归测试后，再决定是否进入产品验收或继续补 aligned RGB-D 等二期能力。

---

## 14. Review Decision Checklist

评审会上建议直接确认以下结论：

- 是否同意 `sensor.camera.rgbd` 作为新增 blueprint id。
- 是否同意第一版只保证同 frame/timestamp，不保证像素级对齐。
- 是否同意 RGB/Depth 分辨率、FOV、relative transform 完全独立。
- 是否同意 Depth 严格沿用 `sensor.camera.depth` 的编码和 converter 语义。
- 是否同意第一版 RGB 只支持 `RGBA`。
- 是否同意验收重点先放在 build、spawn、callback、画面更新、DFS/proto 解析和现有 camera 回归。
- 是否把 aligned depth、calibration metadata、YUV、性能指标放入后续版本。
