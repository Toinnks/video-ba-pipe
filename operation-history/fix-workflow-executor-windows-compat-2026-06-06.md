# 修复 workflow_executor 中 resource_tracker Windows 兼容性问题

## 需求描述

上一轮修复了 `source_workflow_host.py` 和 `decoder_worker.py` 中的 `resource_tracker.unregister` Windows 崩溃问题，但 `workflow_executor.py` 中存在同样的两处调用未修复，导致工作流激活时仍然崩溃（`No module named '_posixsubprocess'`），工作流进入隔离-重试死循环，无法实际执行。

## 当前实现分析

报错调用链：

```
source_workflow_host._activate_workflow()
  → WorkflowExecutor.__init__() / start()
  → workflow_executor.py:767  resource_tracker.unregister(analysis_buffer shm)   ← 崩溃
  → workflow_executor.py:784  resource_tracker.unregister(recording_buffer shm)  ← 同样问题
```

`source_workflow_host.py:163` 捕获异常，将工作流标记为隔离（30s 后重试），但每次重试都在同一行崩溃。

`app/core/workflow_executor.py`：
```python
# line 766-767
shm_name = analysis_buffer_name if os.name == 'nt' else f"/{analysis_buffer_name}"
resource_tracker.unregister(shm_name, 'shared_memory')   # ← 未加 Windows 保护

# line 783-784
shm_name = recording_buffer_name if os.name == 'nt' else f"/{recording_buffer_name}"
resource_tracker.unregister(shm_name, 'shared_memory')   # ← 未加 Windows 保护
```

## 改动方案

与前两次修复完全相同的模式：在两处 `resource_tracker.unregister` 调用外包裹 `if os.name != 'nt':` 判断。

## 涉及文件清单

| 文件路径 | 改动类型 | 改动说明 |
|---------|---------|---------|
| `app/core/workflow_executor.py` | 修改 | line 767、784 各加 `if os.name != 'nt':` 保护 |

## 详细改动说明

### 文件：`app/core/workflow_executor.py`

**原始代码（第 766-767 行）：**
```python
shm_name = analysis_buffer_name if os.name == 'nt' else f"/{analysis_buffer_name}"
resource_tracker.unregister(shm_name, 'shared_memory')
```

**改为：**
```python
shm_name = analysis_buffer_name if os.name == 'nt' else f"/{analysis_buffer_name}"
if os.name != 'nt':
    resource_tracker.unregister(shm_name, 'shared_memory')
```

---

**原始代码（第 783-784 行）：**
```python
shm_name = recording_buffer_name if os.name == 'nt' else f"/{recording_buffer_name}"
resource_tracker.unregister(shm_name, 'shared_memory')
```

**改为：**
```python
shm_name = recording_buffer_name if os.name == 'nt' else f"/{recording_buffer_name}"
if os.name != 'nt':
    resource_tracker.unregister(shm_name, 'shared_memory')
```

## 潜在风险与注意事项

- Linux 行为不变，不影响 Docker 部署
- 这是整个代码库中最后两处未修复的 `resource_tracker.unregister` 调用（已通过全局搜索确认）

## 验证方式

重启 Orchestrator，观察日志不再出现 `No module named '_posixsubprocess'`，且出现工作流正常执行的日志（如检测结果或告警触发）。
