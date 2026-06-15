# 修复工作流算法编排测试中视频测试报错

## 需求描述

在工作流编辑器的"算法编排测试"面板中，使用「上传视频」模式进行测试时会报错，
而使用「上传图片」或「视频源抓帧」模式测试则正常。需要找出原因并修复。

---

## 当前实现分析

### 视频测试 vs 图片测试的代码路径对比

| 维度 | 图片测试 | 视频测试 |
|---|---|---|
| 前端 API | `testWorkflow(id, base64)` → JSON body | `testWorkflowWithFile(id, file)` → FormData |
| 后端入口 | `request.json['image']` | `request.files['media']` |
| 执行函数 | `executor.test_execute()` 调用 **1 次** | `_run_video_test()` → `test_execute()` 调用 **12 次** |

### 问题一：前端 FormData 发送方式不一致（主要嫌疑）

**文件：`frontend/src/services/api.ts`，第 548 行**

```ts
// 视频测试上传（当前实现）
export async function testWorkflowWithFile(workflowId: number, file: File) {
  const formData = new FormData();
  formData.append('media', file);

  return request(`/api/workflows/${workflowId}/test`, {
    method: 'POST',
    data: formData,        // ← 没有 requestType: 'form'
  });
}
```

对比同文件中其他文件上传的实现：
- `uploadVideoFile`（第 270 行）：使用了 `requestType: 'form'`
- `uploadModel`（第 424 行）：明确注释 **"使用原生 fetch API 上传文件，避免 axios 处理 FormData 的问题"**，并改用 `fetch(..., { body: formData })`

`@umijs/max` 的 `request` 默认以 JSON 格式处理 `data`，虽然理论上会检测 `FormData` 实例并特殊处理，但实际上在请求拦截器与 `umi-request` 内部 headers 处理的交互中可能存在问题，导致：
- 服务端收到的 `request.files` 为空，走入 JSON 路径
- 返回 `{'error': '缺少图片数据'}` (400)，或 `{'error': '缺少请求体'}` (400)

### 问题二：视频帧奇数尺寸导致 NV12 转换失败

**文件：`app/core/frame_utils.py`，第 138 行**

```python
def bgr_to_nv12(frame_bgr: np.ndarray) -> np.ndarray:
    height, width = frame_bgr.shape[:2]
    if height % 2 != 0 or width % 2 != 0:
        raise ValueError(f"NV12 requires even dimensions, got {width}x{height}")
```

**文件：`app/web/api/workflow_test.py`，第 294 行**

```python
for index, (frame_idx, second, frame_bgr) in enumerate(sampled_frames, start=1):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    frame_result = executor.test_execute(frame_rgb, frame_bgr)  # ← 未做尺寸校验
```

如果用户上传的视频帧有**奇数宽度或高度**（某些老旧视频、手机录制视频等非标准分辨率），`test_execute` 内部的 `rgb_to_nv12` 会直接抛出 `ValueError`，被外层 `except Exception` 捕获后返回 HTTP 500。

而图片测试时，用户上传的图片通常为标准分辨率（1920×1080、1280×720 等），不会触发此问题。

### 问题三：视频测试缺少逐帧异常隔离

**文件：`app/web/api/workflow_test.py`，第 293 行**

```python
for index, (frame_idx, second, frame_bgr) in enumerate(sampled_frames, start=1):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    frame_result = executor.test_execute(frame_rgb, frame_bgr)
    # ↑ 任何一帧抛出异常都会终止整个循环，也不会返回已处理帧的结果
```

图片测试只处理 1 帧，一旦出错就整体失败是合理的。但视频测试处理 12 帧，单帧失败不应让整个测试崩溃。

---

## 改动方案

1. **将 `testWorkflowWithFile` 改为原生 `fetch`**，彻底绕开 `umi-request`/axios 对 FormData 的处理问题，与 `uploadModel` 保持一致。
2. **在 `_run_video_test` 中对视频帧做偶数维度对齐（crop）**，避免奇数尺寸导致 NV12 转换失败。
3. **为每一帧的 `test_execute` 调用加 try/except**，单帧失败记录后跳过，保证其他帧正常处理。

---

## 涉及文件清单

| 文件路径 | 改动类型 | 改动说明 |
|---|---|---|
| `frontend/src/services/api.ts` | 修改 | `testWorkflowWithFile` 改用原生 fetch，加 Authorization header |
| `app/web/api/workflow_test.py` | 修改 | 视频帧奇数维度对齐；逐帧加 try/except |

---

## 详细改动说明

### 文件一：`frontend/src/services/api.ts`

**原始代码（第 548–556 行）：**
```ts
export async function testWorkflowWithFile(workflowId: number, file: File) {
  const formData = new FormData();
  formData.append('media', file);

  return request(`/api/workflows/${workflowId}/test`, {
    method: 'POST',
    data: formData,
  });
}
```

**改为：**
```ts
export async function testWorkflowWithFile(workflowId: number, file: File) {
  const formData = new FormData();
  formData.append('media', file);

  const token = localStorage.getItem('token');
  const response = await fetch(`/api/workflows/${workflowId}/test`, {
    method: 'POST',
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      // 不设置 Content-Type，让浏览器自动添加 multipart/form-data boundary
    },
    body: formData,
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `请求失败: ${response.status}`);
  }

  return response.json();
}
```

**说明：** 与 `uploadModel` 保持一致，使用原生 `fetch` 发送 FormData，完全避开 `umi-request` 内部可能存在的 FormData 处理问题。

---

### 文件二：`app/web/api/workflow_test.py`

#### 改动点 A：视频帧偶数维度对齐

在 `_run_video_test` 的帧处理循环中，测试帧传入 `test_execute` 前先做尺寸裁剪对齐：

**原始代码（第 293–296 行）：**
```python
for index, (frame_idx, second, frame_bgr) in enumerate(sampled_frames, start=1):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    frame_result = executor.test_execute(frame_rgb, frame_bgr)
```

**改为：**
```python
for index, (frame_idx, second, frame_bgr) in enumerate(sampled_frames, start=1):
    # NV12 要求偶数宽高，将奇数尺寸裁剪为偶数（去掉最后一行/列）
    h, w = frame_bgr.shape[:2]
    if h % 2 != 0 or w % 2 != 0:
        frame_bgr = frame_bgr[:h - (h % 2), :w - (w % 2)]

    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    try:
        frame_result = executor.test_execute(frame_rgb, frame_bgr)
    except Exception as frame_exc:
        logger.warning(f"[WorkflowTest] 视频帧 {frame_idx} 执行失败，跳过: {frame_exc}")
        frame_results.append({
            'frame_index': frame_idx,
            'second': round(second, 3),
            'success': False,
            'detection_count': 0,
            'alert_triggered': False,
            'image_path': None,
            'error': str(frame_exc),
        })
        continue
```

**说明：**
- 裁剪逻辑：`h - (h % 2)` 即奇数时减 1，偶数时不变（`h % 2 == 0` 时 `h - 0 == h`）。裁掉最多 1 像素，对检测效果无实质影响。
- `try/except` 包裹保证单帧失败不终止整个视频测试。

#### 改动点 B：`frame_results.append` 前后对称处理

确保 `frame_result` 为 None 或异常时，`detection_images` 和 `frame_results` 的追加仍然在 `continue` 前完成（参见上方已改动的代码块）。同时在正常路径中不需要改动，因为原始代码在 `continue` 前已经 `append`。

---

## 潜在风险与注意事项

1. **`fetch` 不使用全局请求拦截器**：原来 `request` 有全局的 401 处理（跳转登录页），改用 `fetch` 后需要自行处理。当前改动直接抛出错误即可，前端 `TestPanel.tsx` 已有 catch → 显示错误消息。如果后端真的返回 401，用户需要手动刷新。
2. **裁剪 1px 的影响**：在视频角落/边缘有目标时，裁剪 1px 极小概率导致漏检。可以接受。
3. **单帧失败被跳过**：`frame_results` 会包含 `success: false` 的帧记录，`best_result` 仍然从成功帧中选取。如果所有帧都失败，`best_result` 保持初始的 None，会走到兜底逻辑返回 `'视频抽样帧执行失败'`。
4. **已有图片测试的 401 处理**：`testWorkflow`（图片测试）仍使用 `request`，有全局 401 处理。两者行为有轻微不一致，可在后续统一。

---

## 验证方式

### 手动验证

1. 打开工作流编辑器，进入「算法编排测试」面板
2. 点击「上传视频」，上传一个 MP4 文件（建议先用标准分辨率如 1280×720 验证基本流程）
3. 点击「运行测试」，应返回视频摘要（抽样帧数、命中帧数等）而不是报错
4. 再用分辨率为奇数（如 1279×719）的视频重新测试，应不再报 NV12 维度错误
5. 查看「编排测试结果」页面，应有视频测试记录

### 日志验证

后端日志中不应出现：
- `NV12 requires even dimensions`
- `缺少图片数据` / `缺少请求体`（由 FormData 发送失败导致）

### 测试命令

```bash
# 运行现有测试确保不破坏原有功能
pytest tests/test_workflow_executor_confidence.py
pytest tests/ -k "workflow"
```
