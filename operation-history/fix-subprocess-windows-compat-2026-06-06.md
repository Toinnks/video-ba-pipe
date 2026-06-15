# 修复子进程启动失败（Windows 兼容性问题）

## 需求描述

Orchestrator 启动 `decoder_worker` 和 `source_workflow_host` 子进程后立即退出，导致工作流无法运行。日志显示两个独立错误：
1. `decoder_worker.py`: `ModuleNotFoundError: No module named 'app'`
2. `source_workflow_host.py`: `ModuleNotFoundError: No module named '_posixsubprocess'`

## 当前实现分析

### Bug 1：`decoder_worker.py` 缺少 sys.path 修复

`app/decoder_worker.py:9`：
```python
from app import logger   # 直接导入，无 sys.path 预处理
```

Orchestrator 以子进程方式启动：
```
python.exe D:\...\app\decoder_worker.py --url ...
```

Python 运行脚本文件时，将脚本所在目录（`app/`）加入 `sys.path`，项目根目录不在路径中。因此 `from app import logger` 找不到 `app` 包，退出码 1。

对比 `app/source_workflow_host.py:15`，该文件已有正确处理：
```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```
但 `decoder_worker.py` 遗漏了这一行。

### Bug 2：`source_workflow_host.py` 使用了 POSIX 专属 API

`app/source_workflow_host.py:233-234`：
```python
shm_name = self.source.analysis_buffer_name if os.name == 'nt' else f"/{self.source.analysis_buffer_name}"
resource_tracker.unregister(shm_name, 'shared_memory')
```

`resource_tracker.unregister()` 在首次调用时会尝试启动一个后台追踪进程，内部调用链：
```
resource_tracker.unregister()
  → resource_tracker._send()
  → resource_tracker.ensure_running()
  → util.spawnv_passfds()
  → import _posixsubprocess   ← Windows 不存在此模块
```

`_posixsubprocess` 是 POSIX/Linux 专属 C 扩展模块，Windows 上不提供。代码第233行已对 `shm_name` 做了 Windows/POSIX 区分，但第234行的 `unregister` 调用本身在 Windows 上不可用。

在 Windows 上，共享内存的生命周期由操作系统通过句柄引用计数管理，无需 resource_tracker 干预，跳过该调用即可。

## 改动方案

- **Bug 1**：在 `decoder_worker.py` 的导入语句之前插入 `sys.path.insert`，与 `source_workflow_host.py` 保持一致
- **Bug 2**：将 `resource_tracker.unregister` 调用用 `if os.name != 'nt':` 包裹，Windows 上跳过

## 涉及文件清单

| 文件路径 | 改动类型 | 改动说明 |
|---------|---------|---------|
| `app/decoder_worker.py` | 修改 | 在第9行 `from app import logger` 之前插入 sys.path 修复 |
| `app/source_workflow_host.py` | 修改 | 第234行 resource_tracker.unregister 调用加 Windows 跳过判断 |

## 详细改动说明

### 文件一：`app/decoder_worker.py`

**原始代码（第 1-9 行）：**
```python
import argparse
import logging
import os
import signal
import sys
import time
from multiprocessing import resource_tracker

from app import logger
```

**改为：**
```python
import argparse
import logging
import os
import signal
import sys
import time
from multiprocessing import resource_tracker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import logger
```

**说明：** 子进程以脚本方式启动时，Python 只将脚本所在目录加入 sys.path。`__file__` 为 `app/decoder_worker.py` 的绝对路径，`dirname(dirname(...))` 得到项目根目录，插入后 `app` 包可被正确找到。

---

### 文件二：`app/source_workflow_host.py`

**原始代码（第 233-234 行）：**
```python
shm_name = self.source.analysis_buffer_name if os.name == 'nt' else f"/{self.source.analysis_buffer_name}"
resource_tracker.unregister(shm_name, 'shared_memory')
```

**改为：**
```python
shm_name = self.source.analysis_buffer_name if os.name == 'nt' else f"/{self.source.analysis_buffer_name}"
if os.name != 'nt':
    resource_tracker.unregister(shm_name, 'shared_memory')
```

**说明：** `resource_tracker.unregister` 在 Linux 上的作用是告知资源追踪器"此共享内存由父进程创建，本进程不负责清理"，防止子进程退出时误删共享内存。Windows 上共享内存由 OS 引用计数管理，无此需要，且该调用会触发 `_posixsubprocess` 导入崩溃，应跳过。

## 潜在风险与注意事项

1. **Linux 行为不变**：两处修改均以 `os.name != 'nt'` / `sys.path.insert` 为条件，不影响 Linux/Docker 部署
2. **resource_tracker 跳过的副作用**：Windows 上跳过 unregister 后，Python 的资源追踪器不会知道这块共享内存，但在 Windows 上资源追踪器本来就不管理共享内存（Windows 用句柄引用计数），实际上无影响
3. **decoder_worker 中同样引用了 resource_tracker**：需检查 `decoder_worker.py` 中是否也有类似的 `resource_tracker.unregister` 调用，若有需同样处理

## 验证方式

重启 Orchestrator 后观察日志：
```powershell
python -m app.main
Get-Content app/data/logs/run.log -Wait -Tail 50
```

正常启动日志应出现：
```
创建分析RingBuffer: ...
decoder_worker 启动
WorkflowRunner started for workflow: ...
```

不应再出现 `ModuleNotFoundError: No module named 'app'` 或 `No module named '_posixsubprocess'`。
