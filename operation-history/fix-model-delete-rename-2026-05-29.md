# 修复模型无法删除且无法改名

## 需求描述

模型管理页面存在两个问题：
1. 点击删除按钮后模型未被实际删除（仅显示成功提示，数据库记录和文件均未删除）
2. 没有任何 UI 入口可以修改模型名称，尽管后端 PUT 接口已支持改名

## 当前实现分析

### 问题一：删除功能失效

**文件：** `frontend/src/pages/model-management/index.tsx`，第 126–134 行

```tsx
const handleDelete = async (id: number) => {
  try {
    message.success('模型删除成功');  // ← 直接弹成功提示
    loadModels();                     // ← 重新加载（模型其实未删）
    loadFilterOptions();
  } catch (error: any) {
    message.error('删除失败: ' + error.message);
  }
};
```

`handleDelete` 从未调用 `deleteModel(id)`（API 函数已在 `api.ts` 第 372 行定义），导致每次点击删除都只是刷新列表，实际数据和文件不变。

### 问题二：改名功能缺失

后端 `PUT /api/models/<id>`（`app/web/api/models.py` 第 554–604 行）已支持修改 `name` 字段，前端 `updateModel(id, data)` 函数也已在 `api.ts` 第 365 行定义，但：

- `ModelCard.tsx` 没有编辑/改名按钮
- `DetailModal.tsx` 是纯只读展示，无编辑能力
- `index.tsx` 没有传递任何 `onRename`/`onUpdate` 回调给子组件

## 改动方案

**删除**：在 `handleDelete` 中补上 `await deleteModel(id)` 调用，后端会同时删文件和数据库记录。

**改名**：在 `ModelCard` 上新增编辑图标按钮，点击后弹出一个轻量的 Ant Design `Modal`（内含单个 `Input`），确认后调用 `updateModel`。将弹窗状态和提交逻辑放在 `index.tsx`，`ModelCard` 只负责触发回调，保持组件职责清晰。

不选择在 `DetailModal` 中改造编辑态的原因：该 Modal 当前为只读详情，引入编辑态会增加状态复杂度；而改名是高频操作，放在卡片上更直接。

## 涉及文件清单

| 文件路径 | 改动类型 | 改动说明 |
|---------|---------|---------|
| `frontend/src/pages/model-management/index.tsx` | 修改 | 1. 补全 `handleDelete` 中的 `deleteModel` 调用；2. 新增改名状态和 `handleRename` 逻辑；3. 渲染改名 Modal；4. 向 `ModelCard` 传递 `onRename` prop |
| `frontend/src/pages/model-management/components/ModelCard.tsx` | 修改 | 新增 `onRename` prop 和编辑图标按钮 |

## 详细改动说明

---

### 文件一：`frontend/src/pages/model-management/index.tsx`

**原始代码（第 1–8 行 import 区）：**
```tsx
import { getModels, getModelTypes, getModelFrameworks } from '@/services/api';
```

**改为：**
```tsx
import { getModels, getModelTypes, getModelFrameworks, deleteModel, updateModel } from '@/services/api';
```

**说明：** 补充引入实际需要调用的 API 函数。

---

**原始代码（第 46–47 行，state 区）：**
```tsx
const [detailModalVisible, setDetailModalVisible] = useState(false);
const [selectedModel, setSelectedModel] = useState<Model | null>(null);
```

**改为：**
```tsx
const [detailModalVisible, setDetailModalVisible] = useState(false);
const [selectedModel, setSelectedModel] = useState<Model | null>(null);
const [renameModalVisible, setRenameModalVisible] = useState(false);
const [renameTarget, setRenameTarget] = useState<Model | null>(null);
const [renameName, setRenameName] = useState('');
const [renameLoading, setRenameLoading] = useState(false);
```

**说明：** 新增改名弹窗所需的状态。

---

**原始代码（第 126–134 行）：**
```tsx
const handleDelete = async (id: number) => {
  try {
    message.success('模型删除成功');
    loadModels();
    loadFilterOptions();
  } catch (error: any) {
    message.error('删除失败: ' + error.message);
  }
};
```

**改为：**
```tsx
const handleDelete = async (id: number) => {
  try {
    await deleteModel(id);
    message.success('模型删除成功');
    loadModels();
    loadFilterOptions();
  } catch (error: any) {
    message.error('删除失败: ' + error.message);
  }
};
```

**说明：** 补上实际删除调用，后端会同步删除物理文件和数据库记录。

---

**在 `handleDelete` 之后新增改名相关函数：**
```tsx
const handleRenameOpen = (model: Model) => {
  setRenameTarget(model);
  setRenameName(model.name);
  setRenameModalVisible(true);
};

const handleRenameConfirm = async () => {
  if (!renameTarget) return;
  const trimmed = renameName.trim();
  if (!trimmed) {
    message.warning('模型名称不能为空');
    return;
  }
  setRenameLoading(true);
  try {
    await updateModel(renameTarget.id, { name: trimmed });
    message.success('模型名称已更新');
    setRenameModalVisible(false);
    loadModels();
  } catch (error: any) {
    message.error('改名失败: ' + error.message);
  } finally {
    setRenameLoading(false);
  }
};
```

---

**在 `ModelCard` 的渲染处（第 181–188 行）：**

**原始代码：**
```tsx
<ModelCard
  model={model}
  onView={showDetail}
  onDelete={handleDelete}
/>
```

**改为：**
```tsx
<ModelCard
  model={model}
  onView={showDetail}
  onDelete={handleDelete}
  onRename={handleRenameOpen}
/>
```

---

**在 `</UploadModal>` 之后、`</div>` 之前新增改名 Modal：**
```tsx
<Modal
  title="修改模型名称"
  open={renameModalVisible}
  onCancel={() => setRenameModalVisible(false)}
  onOk={handleRenameConfirm}
  confirmLoading={renameLoading}
  okText="确认"
  cancelText="取消"
>
  <Input
    value={renameName}
    onChange={(e) => setRenameName(e.target.value)}
    onPressEnter={handleRenameConfirm}
    maxLength={100}
    placeholder="请输入新的模型名称"
  />
</Modal>
```

**说明：** 轻量弹窗，只包含一个输入框，支持回车确认。需要在文件顶部从 `antd` 额外引入 `Modal` 和 `Input`。

---

### 文件二：`frontend/src/pages/model-management/components/ModelCard.tsx`

**原始代码（第 16–32 行，接口定义）：**
```tsx
interface ModelCardProps {
  model: { ... };
  onView: (model: any) => void;
  onDelete: (id: number) => void;
}
```

**改为：**
```tsx
interface ModelCardProps {
  model: { ... };
  onView: (model: any) => void;
  onDelete: (id: number) => void;
  onRename: (model: any) => void;
}
```

---

**原始代码（第 34 行，组件签名）：**
```tsx
const ModelCard: React.FC<ModelCardProps> = ({ model, onView, onDelete }) => {
```

**改为：**
```tsx
const ModelCard: React.FC<ModelCardProps> = ({ model, onView, onDelete, onRename }) => {
```

---

**原始代码（第 6–9 行，图标 import）：**
```tsx
import {
  EyeOutlined,
  CopyOutlined,
  DeleteOutlined,
  ApiOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
```

**改为：**
```tsx
import {
  EyeOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ApiOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
```

---

**原始代码（第 133–142 行，复制按钮之后、删除按钮之前）：**
```tsx
<Tooltip title="复制路径">
  <button
    type="button"
    className="action-btn action-btn-copy"
    onClick={handleCopyPath}
  >
    <CopyOutlined />
  </button>
</Tooltip>
{model.usage_count === 0 && (
```

**改为（在 Tooltip 复制路径 后紧接新增改名按钮）：**
```tsx
<Tooltip title="复制路径">
  <button
    type="button"
    className="action-btn action-btn-copy"
    onClick={handleCopyPath}
  >
    <CopyOutlined />
  </button>
</Tooltip>
<Tooltip title="改名">
  <button
    type="button"
    className="action-btn action-btn-copy"
    onClick={() => onRename(model)}
  >
    <EditOutlined />
  </button>
</Tooltip>
{model.usage_count === 0 && (
```

**说明：** 复用已有 `action-btn-copy` 样式（中性色调），避免引入新 CSS。改名对所有模型（含被使用的）均可操作，不受 `usage_count` 限制，因为改名不影响文件路径。

## 潜在风险与注意事项

1. **改名唯一性**：后端 `update_model` 未校验新名称是否与其他模型重名（`name+version` 组合才是唯一键）。如果用户改成重复名称，后端会静默保存，暂不影响功能，可后续按需加校验。
2. **被使用的模型改名**：`usage_count > 0` 的模型也允许改名，因为算法引用的是 `file_path`（不随改名变化），改名安全。
3. **删除的竞态**：`handleDelete` 现在是 async，Popconfirm 的 `onConfirm` 接受 Promise，Ant Design 会自动处理加载态，无需额外修改。

## 验证方式

**删除验证：**
1. 上传一个测试模型
2. 点击模型卡片上的删除按钮，确认弹窗
3. 确认后模型从列表消失，服务器上对应文件被删除
4. 对 `usage_count > 0` 的模型点击删除，应提示"正在被 N 个算法使用，无法删除"（后端已有此保护）

**改名验证：**
1. 点击模型卡片上的编辑（铅笔）图标
2. 弹窗出现，输入框预填当前名称
3. 修改名称后点击确认
4. 卡片上名称更新为新名称
5. 清空输入框直接点击确认，应提示"模型名称不能为空"
