# 修复视频源预览看不到画面

## 需求描述

视频源管理页面点击预览时，后台日志显示帧捕获成功（HTTP 200），但前端弹框始终不显示图片，只显示"加载中..."转圈。

## 当前实现分析

### 数据链路（正常）

后端 `capture_frame_from_source`（`app/web/api/workflows.py:284`）：
1. 优先读取运行中视频源的快照文件
2. 否则直接用 OpenCV 连接 RTSP 捕帧
3. 返回 `{ "success": true, "image": "data:image/jpeg;base64,..." }`

前端调用链：
- `captureFrame(source.id)` → `GET /api/workflows/capture_frame/{id}` → 返回整个 JSON 对象
- `handlePreview`（`frontend/src/pages/video-sources/index.tsx:98`）：

```tsx
const res = await captureFrame(source.id);
setPreviewSrc(res.image);   // 正确，res.image 是 "data:image/jpeg;base64,..."
```

数据链路无误，问题在 `ImagePreview` 组件的渲染逻辑。

### 根本原因：`ImagePreview` 内部 `loading` 状态竞态条件

`frontend/src/components/common/ImagePreview/index.tsx`：

```tsx
const [loading, setLoading] = useState(true);

useEffect(() => {
  if (visible) {
    setLoading(true);   // ← 问题所在
    setError(false);
  }
}, [visible, src]);   // ← src 是依赖项
```

渲染逻辑：
```tsx
<Image
  src={src}
  style={{ display: loading ? 'none' : 'block' }}  // loading=true 时图片隐藏
  onLoad={() => setLoading(false)}                 // 加载完成后才显示
/>
```

**竞态条件复现步骤：**

1. `src` 从 `''` 变为 `'data:image/jpeg;base64,...'`（API 返回后）
2. React 重新渲染，挂载 `<Image>` 并设置 `src` 属性（`display: none`）
3. 浏览器开始加载 base64 图片（极快，以**微任务**执行）
4. `onLoad` 触发 → `setLoading(false)` → 图片本应显示
5. **但**：`useEffect([visible, src])` 依赖了 `src`，作为**宏任务**在 `onLoad` 之后执行
6. `setLoading(true)` 将 loading 重置为 true → 图片再次隐藏
7. 此时 `onLoad` 不会再次触发（图片已加载完毕），`loading` 永久为 `true`

结果：图片始终 `display: none`，用户只看到转圈。

**关键原因**：base64 数据 URI 加载速度极快，其 `load` 事件以微任务形式触发，早于 `useEffect`（宏任务）执行。`useEffect` 在 `onLoad` 之后运行并覆盖了 `loading = false`。

### 多余的内部状态

父组件（`index.tsx`）已经通过 `previewSrc` 管理三种状态：
- `''`：API 调用中，显示加载中
- `'error'`：捕帧失败，显示错误
- `'data:...'`：成功，显示图片

`ImagePreview` 内部再维护一个 `loading` 状态是**多余且有害**的。

## 改动方案

**移除 `ImagePreview` 内部的 `loading` 状态**，直接根据 `src` prop 决定渲染分支：

- `src === ''`：显示加载转圈（API 调用中）
- `src === 'error'`：显示错误提示
- 其他值：直接渲染 `<Image>`，不再使用 `display: none` 隐藏技巧

不再需要 `onLoad` 回调，不再有竞态窗口。

## 涉及文件清单

| 文件路径 | 改动类型 | 改动说明 |
|---------|---------|---------|
| `frontend/src/components/common/ImagePreview/index.tsx` | 修改 | 移除内部 `loading` state 和 `useEffect`，改为纯 `src` prop 驱动 |

无需修改后端代码。

## 详细改动说明

### 文件：`frontend/src/components/common/ImagePreview/index.tsx`

**原始代码：**

```tsx
const ImagePreview: React.FC<ImagePreviewProps> = ({
  visible, src, alt = '预览图片', title, onClose,
}) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (visible) {
      setLoading(true);
      setError(false);
    }
  }, [visible, src]);

  const isError = src === 'error';

  return (
    <Modal ...>
      <div className="preview-container">
        {title && <div className="preview-title">{title}</div>}
        <div className="preview-image-wrapper">
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
              onError={() => { setLoading(false); setError(true); }}
            />
          ) : null}
          {loading && !isError && !error && (
            <div className="preview-loading">
              <div className="loading-spinner" />
              <div className="loading-text">加载中...</div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
};
```

**改为：**

```tsx
const ImagePreview: React.FC<ImagePreviewProps> = ({
  visible, src, alt = '预览图片', title, onClose,
}) => {
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    if (visible) {
      setImgError(false);
    }
  }, [visible, src]);

  const isError = src === 'error' || imgError;
  const isLoading = !src && !isError;

  return (
    <Modal ...>
      <div className="preview-container">
        {title && <div className="preview-title">{title}</div>}
        <div className="preview-image-wrapper">
          {isError ? (
            <div className="preview-error">
              <div className="error-icon">⚠</div>
              <div className="error-text">无法加载预览图片</div>
            </div>
          ) : isLoading ? (
            <div className="preview-loading">
              <div className="loading-spinner" />
              <div className="loading-text">加载中...</div>
            </div>
          ) : (
            <Image
              src={src}
              alt={alt}
              className="preview-image"
              preview={false}
              onError={() => setImgError(true)}
            />
          )}
        </div>
      </div>
    </Modal>
  );
};
```

**说明：**
- 移除 `loading` state，消除与 `onLoad` 的竞态条件
- 改为根据 `src` prop 的值直接决定渲染分支：空字符串→转圈，`'error'`→错误，其他→图片
- 保留 `imgError` state 处理图片本身加载失败的情况（网络问题、损坏的 base64 等）
- 删除 `display: none` 隐藏技巧和 `onLoad` 回调
- 父组件 `handlePreview` 已正确维护三态（`''` / `'error'` / `'data:...'`），无需修改

## 潜在风险与注意事项

1. **CSS 类名 `loading` 的移除**：原代码中 `<Image className={... loading ? 'loading' : ''}>` 会附加 `loading` class。如果 `index.css` 中有针对该 class 的样式（如透明度过渡动画），需要检查并清理，避免样式残留影响。
2. **首次打开时无过渡动画**：原来通过 `display: none` → `block` 实现隐式淡入。新实现是 `<Image>` 组件直接挂载，无此过渡。Ant Design 的 `Image` 组件自身有加载占位行为，视觉上应无明显差异。
3. **大图加载延迟**：新实现中图片直接渲染，对于网络传输较慢的场景（如非 base64 的 URL 图片），没有"加载中"指示。当前场景全部是 base64（即时加载），无影响。

## 验证方式

1. 打开视频源管理页面
2. 点击任意视频源的"预览"按钮
3. **预期**：弹框出现后约3-5秒内显示捕获的画面，不再卡在"加载中..."
4. 关闭后再次点击预览，**预期**：可以再次正常显示
5. 测试网络异常情况（断开视频源）：**预期**：显示"无法加载预览图片"错误提示
