# 修复视频源预览功能无法显示图片

## 问题描述

视频源列表页面点击预览按钮后，前端直接请求静态快照文件 `/api/image/snapshots/{source_code}.jpg`，导致以下问题：

1. 视频源刚启动时（< 100 帧），快照文件尚未生成 → HTTP 404 → "无法加载预览图片"
2. 低帧率流（如 1fps）需等约 100 秒才生成第一张快照
3. 重启后旧快照不会立即刷新

---

## 涉及文件

| 文件 | 修改内容 |
|------|---------|
| `app/decoder_worker.py` | 快照触发条件加入第 1 帧 |
| `frontend/src/pages/video-sources/index.tsx` | 改用 `captureFrame` API 获取 base64 图片 |
| `frontend/src/components/common/ImagePreview/index.tsx` | 处理空 src 保持 loading 状态，处理错误 sentinel |

---

## 修改 1：`app/decoder_worker.py`

### 原始代码（第 370 行）

```python
if frame_count % 100 == 0 and wrote_analysis:
    logger.info(
        f"已解码 {frame_count} 帧, "
        f"分析写入 {analysis_written_count} 帧, "
        f"分析跳过 {analysis_skipped_count} 帧, "
        f"录制写入 {recording_written_count} 帧"
    )
    self.snapshot(frame)
```

### 修改后代码

```python
if (frame_count == 1 or frame_count % 100 == 0) and wrote_analysis:
    logger.info(
        f"已解码 {frame_count} 帧, "
        f"分析写入 {analysis_written_count} 帧, "
        f"分析跳过 {analysis_skipped_count} 帧, "
        f"录制写入 {recording_written_count} 帧"
    )
    self.snapshot(frame)
```

### 说明

加入 `frame_count == 1` 条件，使视频源解码第一帧写入分析缓冲区时立即保存一张快照，保证文件在视频源启动后即刻存在。

---

## 修改 2：`frontend/src/pages/video-sources/index.tsx`

### 原始代码

```typescript
// import 部分（第 8-13 行）
import {
  getVideoSources,
  createVideoSource,
  updateVideoSource,
  deleteVideoSource,
} from '@/services/api';

// 状态（第 27 行）
const [previewSource, setPreviewSource] = useState<any>(null);

// handlePreview（第 96-99 行）
const handlePreview = (source: any) => {
  setPreviewSource(source);
  setPreviewVisible(true);
};

// ImagePreview 调用（第 153-158 行）
<ImagePreview
  visible={previewVisible}
  src={`/api/image/snapshots/${previewSource?.source_code}.jpg`}
  title={previewSource?.name}
  onClose={() => setPreviewVisible(false)}
/>
```

### 修改后代码

```typescript
// import 部分：新增 captureFrame
import {
  getVideoSources,
  createVideoSource,
  updateVideoSource,
  deleteVideoSource,
  captureFrame,
} from '@/services/api';

// 新增状态
const [previewSrc, setPreviewSrc] = useState<string>('');

// handlePreview 改为 async，调用 captureFrame API
const handlePreview = async (source: any) => {
  setPreviewSource(source);
  setPreviewSrc('');        // 清空旧图，让 modal 先显示 loading
  setPreviewVisible(true);
  try {
    const res = await captureFrame(source.id);
    setPreviewSrc(res.image);   // base64 data URL
  } catch (e) {
    setPreviewSrc('error');     // 触发错误显示
  }
};

// ImagePreview 使用 previewSrc 状态
<ImagePreview
  visible={previewVisible}
  src={previewSrc}
  title={previewSource?.name}
  onClose={() => setPreviewVisible(false)}
/>
```

### 说明

- 不再使用静态快照 URL，改为调用 `/api/workflows/capture_frame/<id>` 接口
- 该接口逻辑：若视频源 RUNNING 且快照存在则毫秒级返回；否则直连视频源（5-10 秒）
- 先打开 modal 再异步加载图片，用户立即看到 loading 动画而不是空白/报错
- 错误时设置 sentinel 值 `'error'` 传给 ImagePreview

---

## 修改 3：`frontend/src/components/common/ImagePreview/index.tsx`

### 原始代码（第 23-72 行）

```typescript
useEffect(() => {
  if (visible) {
    setLoading(true);
    setError(false);
  }
}, [visible, src]);

// 渲染部分
{error ? (
  <div className="preview-error">
    <div className="error-icon">⚠</div>
    <div className="error-text">无法加载预览图片</div>
  </div>
) : (
  <Image
    src={src}
    alt={alt}
    className={`preview-image ${loading ? 'loading' : ''}`}
    style={{ display: loading ? 'none' : 'block' }}
    preview={false}
    onLoad={() => setLoading(false)}
    onError={() => {
      setLoading(false);
      setError(true);
    }}
  />
)}
{loading && !error && (
  <div className="preview-loading">
    <div className="loading-spinner" />
    <div className="loading-text">加载中...</div>
  </div>
)}
```

### 修改后代码

```typescript
useEffect(() => {
  if (visible) {
    setLoading(true);
    setError(false);
  }
}, [visible, src]);

const isError = src === 'error';   // 新增：识别错误 sentinel

// 渲染部分
{isError || error ? (
  <div className="preview-error">
    <div className="error-icon">⚠</div>
    <div className="error-text">无法加载预览图片</div>
  </div>
) : src ? (
  <Image
    src={src}
    alt={alt}
    className={`preview-image ${loading ? 'loading' : ''}`}
    style={{ display: loading ? 'none' : 'block' }}
    preview={false}
    onLoad={() => setLoading(false)}
    onError={() => {
      setLoading(false);
      setError(true);
    }}
  />
) : null}
{loading && !isError && !error && (
  <div className="preview-loading">
    <div className="loading-spinner" />
    <div className="loading-text">加载中...</div>
  </div>
)}
```

### 说明

- `src === ''`（空字符串）时不渲染 `<Image>`，避免浏览器对空 src 立即触发 `onError` 导致 loading 变成 error
- `src === 'error'`（sentinel 值）时直接显示错误提示，不经过图片加载流程
- `src` 为有效 URL/base64 时正常渲染图片，加载完成后隐藏 spinner

---

## 修复效果

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| 视频源刚启动，立即预览 | 404 → 报错 | 第一帧写入后即有快照，毫秒级返回 |
| 视频源运行中预览 | 静态文件可能 60 秒才刷新 | 实时调用 captureFrame，返回最新快照 |
| 视频源已停止预览 | 404 | 直连视频源抓帧（5-10s），失败则显示错误 |
| 低帧率流（1fps）预览 | 等 100 秒 | 第 1 帧即保存快照，1 秒内可预览 |
