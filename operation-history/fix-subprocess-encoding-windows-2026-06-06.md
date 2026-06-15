# 修复子进程输出 GBK 编码崩溃导致工作流日志丢失

## 需求描述

Orchestrator 在 Windows 上读取 source_workflow_host 子进程的 stdout 时因 GBK 解码失败而崩溃，`OutputReader` 线程退出，之后所有工作流执行日志不可见，工作流是否正常运行无法判断。

## 当前实现分析

### 错误链

`orchestrator.py:61` 报错：
```
[SourceHost-1] 读取stdout时出错: 'gbk' codec can't decode byte 0xae in position 134
```

`OutputReader.run()`（`orchestrator.py:47-61`）：
```python
def run(self):
    try:
        for line in iter(self.stream.readline, ''):   # ← 逐行读取，GBK 解码失败即抛异常
            ...
    except Exception as e:
        if self.running:
            logger.warning(f"[{self.log_label}] 读取{self.stream_type}时出错: {e}")
        # ← 异常后线程退出，不再读取任何输出
```

`subprocess.Popen`（`orchestrator.py:454`）：
```python
workflow_p = subprocess.Popen(
    workflow_args,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    universal_newlines=True,   # ← 等价于 text=True，使用系统默认编码（Windows 为 GBK）
    bufsize=1
)
```

`universal_newlines=True` 在 Windows 上使用系统默认编码（GBK/CP936）打开 stream。子进程输出包含 UTF-8 中文字符和 emoji（如 🚨 ✅），GBK 无法解码这些字节，`readline()` 抛出 `UnicodeDecodeError`，`OutputReader` 线程崩溃退出。

**后果**：工作流可能在正常运行，但所有输出对 Orchestrator 完全不可见，无法诊断问题。

### 子进程自身的输出编码

子进程（`source_workflow_host.py`）运行时，Python 的 stdout 编码也受系统默认编码影响。若不设置 `PYTHONIOENCODING`，子进程写 stdout 时同样可能因编码不匹配产生乱码。

## 改动方案

1. 将 `Popen` 的 `universal_newlines=True` 改为 `encoding='utf-8', errors='replace'`，强制用 UTF-8 解码子进程输出，不可解码的字节替换为 `?` 而非抛异常
2. 通过 `env` 参数给子进程注入 `PYTHONIOENCODING=utf-8`，确保子进程 Python 也用 UTF-8 输出

## 涉及文件清单

| 文件路径 | 改动类型 | 改动说明 |
|---------|---------|---------|
| `app/core/orchestrator.py` | 修改 | source_workflow_host 的 Popen 调用：替换编码参数，添加环境变量 |

## 详细改动说明

### 文件：`app/core/orchestrator.py`

**原始代码（第 454-460 行）：**
```python
workflow_p = subprocess.Popen(
    workflow_args,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    universal_newlines=True,
    bufsize=1
)
```

**改为：**
```python
child_env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
workflow_p = subprocess.Popen(
    workflow_args,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    encoding='utf-8',
    errors='replace',
    bufsize=1,
    env=child_env,
)
```

**说明：**
- `universal_newlines=True` → `encoding='utf-8', errors='replace'`：强制 UTF-8 解码，`errors='replace'` 确保任何无法解码的字节都替换为 `?` 而不是抛异常，`OutputReader` 线程不再崩溃
- `env=child_env`：注入 `PYTHONIOENCODING=utf-8`，子进程 Python 解释器也用 UTF-8 处理 stdout/stderr

## 潜在风险与注意事项

- `os` 已在本次修复前加入顶部 import，可直接使用 `os.environ`
- `errors='replace'` 会将不可解码字节替换为 `?`，极少数情况下日志中可能出现 `?` 占位符，但不影响功能
- Linux 环境下 `PYTHONIOENCODING` 通常已为 UTF-8，加入此变量无副作用

## 验证方式

重启 Orchestrator 后，`[SourceHost-1]` 的日志应持续出现（包括工作流执行帧处理、算法检测结果等），不再出现 `读取stdout时出错` 警告。
