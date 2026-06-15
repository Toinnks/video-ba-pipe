# 修复模型删除无效（显示成功但未实际删除）

## 需求描述

模型管理页面点击删除并确认后，提示"模型删除成功"，但刷新后模型仍然存在，实际并未删除。

## 当前实现分析

### 后端（正常）

`app/web/api/models.py:607` 的 `DELETE /api/models/<id>` 接口逻辑完整：
1. 检查模型是否被算法使用（`usage_count > 0` 则拒绝）
2. 删除磁盘文件
3. `model.delete_instance()` 删除数据库记录
4. 返回 `{ "success": true, "message": "模型删除成功" }`

### 前端（存在 Bug）

`frontend/src/pages/model-management/index.tsx:126-134`：

```tsx
const handleDelete = async (id: number) => {
  try {
    message.success('模型删除成功');   // ← 直接弹成功，没有调用任何 API！
    loadModels();                      // ← 刷新列表（模型仍在，因为根本没删）
    loadFilterOptions();
  } catch (error: any) {
    message.error('删除失败: ' + error.message);
  }
};
```

**根本原因**：`handleDelete` 缺少对 `deleteModel(id)` 的调用。函数直接弹成功提示并刷新列表，既没有发出 DELETE 请求，也没有 import `deleteModel`。

`deleteModel` 已在 `api.ts:238` 中定义，但 `index.tsx` 的 import 语句（第7行）只导入了 `getModels, getModelTypes, getModelFrameworks`，遗漏了 `deleteModel`。

## 改动方案

在 `handleDelete` 中补上 `await deleteModel(id)` 调用，并在 import 中添加 `deleteModel`。两处改动，均在同一文件。

## 涉及文件清单

| 文件路径 | 改动类型 | 改动说明 |
|---------|---------|---------|
| `frontend/src/pages/model-management/index.tsx` | 修改 | 补全 `deleteModel` import；在 `handleDelete` 中添加 API 调用 |

## 详细改动说明

### 文件：`frontend/src/pages/model-management/index.tsx`

**改动1 — 第 7 行，补全 import：**

原始代码：
```tsx
import { getModels, getModelTypes, getModelFrameworks } from '@/services/api';
```

改为：
```tsx
import { getModels, getModelTypes, getModelFrameworks, deleteModel } from '@/services/api';
```

**改动2 — 第 126-134 行，补全 API 调用：**

原始代码：
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

改为：
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

**说明：**
- `await deleteModel(id)` 发出 `DELETE /api/models/<id>` 请求
- 后端若返回非 2xx 状态（如模型仍在使用），umi request 会 throw，catch 块展示错误信息
- 成功后再刷新列表，确保 UI 与实际数据一致

## 潜在风险与注意事项

- 无副作用，改动范围极小，仅补全遗漏调用
- 后端已有保护：若模型被算法引用（`usage_count > 0`）会返回 400，前端 catch 块会展示错误原因

## 验证方式

1. 上传一个测试模型
2. 在模型管理页面点击该模型卡片的删除按钮
3. 确认弹框后，**预期**：提示"模型删除成功"，列表中该模型消失
4. 刷新页面，**预期**：模型不再出现
5. 对正在被算法使用的模型执行删除，**预期**：显示"删除失败：该模型正在被 N 个算法使用，无法删除"
