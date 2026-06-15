# 启动手册（源码级）

> 本文档严格基于源码推导，所有行为均可对照代码验证。
> 对照文件：`app/main.py`、`app/core/orchestrator.py`、`app/config.py`、`app/setup_database.py`

---

## 1. 系统架构概览

系统由三类独立进程构成：

```
[终端 A] python -m app.main
            └─ Orchestrator.run()  ← 每5秒一个主循环
                 ├─ [子进程] decoder_worker.py --source-id <id>      # 每个视频源一个
                 │    解码流 → VideoRingBuffer (分析) + CompressedVideoRingBuffer (录制)
                 └─ [子进程] source_workflow_host.py --source-id <id> # 每个视频源一个
                       └─ [WorkflowRunner 线程] × N                  # 每个工作流一个线程
                             └─ WorkflowExecutor.run_once()

[终端 B] python app/web/webapp.py
            Flask HTTP API，监听 0.0.0.0:5002
```

进程间通信通过共享内存完成，不经过网络 socket。

---

## 2. 本地开发启动

前端是独立的 React/UmiJS SPA，需单独启动开发服务器。Flask（:5002）仅提供 REST API，不渲染 HTML 页面。

### 方式 B：手动分终端启动

```bash
# 终端 1：初始化并启动 Flask 后端 API
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m app.setup_database    # 建表 + 创建默认账号（幂等）
python -m app.web.webapp        # 监听 0.0.0.0:5002

# 终端 2（可选）：启动 AI 分析引擎
python -m app.main

# 终端 3：启动前端开发服务器
cd frontend
npm install
npm run dev                     # UmiJS 默认监听 http://localhost:8000
```

**访问地址：http://localhost:8000**（不是 5002）
**默认账号：`admin / admin123`**（由 setup_database.py 自动创建）

> `frontend/.umirc.ts` 中的 proxy target 已设置为 `http://localhost:5002`，
> `/api` 请求会自动转发到 Flask 后端。

---

## 3. 启动内部时序

```
T+0.0s  main.py
          调用 setup_database()
            → 按5个优先级批次建17张表
            → 首次运行：INSERT admin用户（admin / admin123）
            → 补齐历史库缺失字段（向前兼容 ALTER TABLE）
            → 创建8个数据目录（见第5节）

T+0.1s  Orchestrator.__init__()
          VideoSource.update(status='STOPPED').execute()
            ← 重置所有源状态（防止上次异常退出残留 RUNNING 状态）
          AlertMediaCleaner 初始化

T+0.5s  orchestrator.run()
          media_cleaner.start()  ← 告警媒体清理后台线程启动

T+0.5s  第一轮 manage_sources()
          查询：enabled=True AND status='STOPPED' 的 VideoSource
          对每个源：
            1. 创建 VideoRingBuffer
                 名称：video_buffer.analysis.{source_code}
                 容量：ANALYSIS_TARGET_FPS × ANALYSIS_BUFFER_SECONDS 帧
            2. 创建 CompressedVideoRingBuffer
                 名称：video_buffer.recording.{source_code}
                 容量：RECORDING_BUFFER_DURATION 秒
            3. 启动子进程 decoder_worker.py（见第4节命令行参数）
            4. VideoSource.status → 'RUNNING'

T+1.0s  第一轮 manage_workflows()
          查询：is_active=True 的 Workflow，按 source_id 分组
          对每组：
            启动子进程 source_workflow_host.py --source-id <id>
              → 连接分析缓冲区（最多重试10次，间隔1s）
              → 每个工作流启动一个 WorkflowRunner 线程

T+5.0s  第二轮主循环（健康检查逻辑开始运行，但60s宽限期内跳过重启）

T+60s   健康检查完全生效
          无帧时长 > NO_FRAME_CRITICAL_THRESHOLD(30s) → 重启视频源
          source host 进程退出 → 自动重新拉起
```

---

## 4. decoder_worker.py 启动参数

Orchestrator 按以下方式构造命令（对应 `app/core/orchestrator.py`）：

```bash
python app/decoder_worker.py \
  --url         <source.url>             \  # 视频源 URL（RTSP/HTTP-FLV/HLS/本地文件）
  --source-id   <source.id>              \
  --decoder-type ffmpeg_sw               \  # 来自 VIDEO_DECODER_TYPE（默认 ffmpeg_sw）
  --width       1920                     \  # 来自 source.width（数据库配置）
  --height      1080                     \  # 来自 source.height
  --output-format nv12                   \  # 来自 VIDEO_FRAME_PIXEL_FORMAT（默认 nv12）
  --analysis-fps 3                       \  # 来自 ANALYSIS_TARGET_FPS（默认 3）
  --recording-fps 10                        # 来自 RECORDING_FPS（默认 10）
```

解码器选项（`VIDEO_DECODER_TYPE`）：

| 值 | 适用场景 |
|----|---------|
| `ffmpeg_sw` | 默认，CPU 软解码 |
| `nvdec` | NVIDIA GPU 硬解码 |
| `rk_mpp` | 瑞芯微 RK3588 硬解码 |

---

## 5. 自动创建目录

`config.py` 在模块导入时自动创建以下目录（`os.makedirs(..., exist_ok=True)`）：

| 环境变量 | 本地默认路径 | Docker 路径 |
|---------|------------|------------|
| `DB_PATH` | `app/data/db` | — |
| `FRAME_SAVE_PATH` | `app/data/frames` | `/data/frames` |
| `VIDEO_SAVE_PATH` | `app/data/videos` | `/data/videos` |
| `VIDEO_SOURCE_PATH` | `app/data/video_sources` | `/data/video_sources` |
| `MODEL_SAVE_PATH` | `app/data/models` | `/data/models` |
| `USER_SCRIPTS_ROOT` | `app/data/user_scripts` | `/data/user_scripts` |
| `LOG_SAVE_PATH` | `app/data/logs` | `/data/logs` |
| `SNAPSHOT_SAVE_PATH` | `app/data/snapshots` | `/data/snapshots` |

---

## 6. 日志文件

所有日志写入 `app/data/logs/`（`LOG_SAVE_PATH`）：

| 文件 | 内容 |
|------|------|
| `run.log` | 主进程运行日志（Orchestrator 事件） |
| `debug.log` | 详细调试日志 |
| `workflow.log` | 工作流执行日志（节点调度、告警触发） |
| `workflow_debug.log` | 工作流调试日志 |
| `detection_results_YYYYMMDD.jsonl` | 检测结果（需 `DETECTION_JSONL_LOG_ENABLED=true`） |

---

## 7. 首次使用检查清单

系统启动后，工作流需满足以下条件才会运行：

1. **视频源**：`VideoSource.enabled = True`（Web UI 中启用）
2. **工作流**：`Workflow.is_active = True`（Web UI 中激活）
3. **工作流节点**：至少包含一个 SourceNode 和一个 AlgorithmNode
4. **算法脚本**：脚本文件存在于 `USER_SCRIPTS_ROOT`（默认 `app/data/user_scripts/`）
5. **模型文件**：模型文件存在于 `MODEL_SAVE_PATH`（默认 `app/data/models/`）

Orchestrator 主循环每5秒轮询一次数据库，配置变更无需重启主进程。

---

## 8. 关键参数速查

### 解码与管道

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `VIDEO_DECODER_TYPE` | `ffmpeg_sw` | 解码器类型 |
| `VIDEO_FRAME_PIXEL_FORMAT` | `nv12` | 帧像素格式 |
| `IS_EXTREME_DECODE_MODE` | `false` | 跳过中间帧（低配设备） |
| `FFMPEG_SW_DECODER_THREADS` | `1` | 每个解码器的线程数 |
| `DECODER_OUTPUT_QUEUE_SIZE` | `5` | 解码输出队列深度 |

### 分析缓冲区

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ANALYSIS_TARGET_FPS` | `3` | 工作流采样率（帧/秒） |
| `ANALYSIS_BUFFER_SECONDS` | `5` | 分析环形缓冲区时长 |

### 录制

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `RECORDING_ENABLED` | `true` | 启用录制 |
| `RECORDING_BUFFER_DURATION` | — | 录制缓冲区时长（须 ≥ PRE + POST）|
| `PRE_ALERT_DURATION` | `5` | 告警前录制时长（秒） |
| `POST_ALERT_DURATION` | `5` | 告警后录制时长（秒） |
| `RECORDING_FPS` | `5` | 录制输出帧率 |
| `RECORDING_JPEG_QUALITY` | `85` | 压缩缓冲区 JPEG 质量 |

### 告警

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ALERT_SUPPRESSION_DURATION` | `10` | 同类告警冷却时间（秒） |

---

## 9. 健康检查机制

Orchestrator 主循环包含自动恢复逻辑（60秒宽限期后生效）：

| 参数（config.py:168-190） | 默认值 | 触发行为 |
|--------------------------|--------|---------|
| `NO_FRAME_WARNING_THRESHOLD` | `15s` | 写入警告日志 |
| `NO_FRAME_CRITICAL_THRESHOLD` | `30s` | 重启 decoder_worker 进程 |
| `HIGH_ERROR_COUNT_THRESHOLD` | `10` | 写入警告日志 |
| `MAX_CONSECUTIVE_ERRORS` | `60` | decoder 主动退出（触发 Orchestrator 重拉） |
| `HEALTH_MONITOR_ENABLED` | `true` | 是否启用健康检查 |

source_workflow_host 内部恢复：单个工作流线程连续错误10次后隔离30秒，之后自动重试。

---

## 10. 优雅关闭

向主进程发送 `SIGINT`（Ctrl+C）或 `SIGTERM`，触发以下有序关闭流程：

```
信号接收
  → orchestrator.stop()
       1. media_cleaner.stop()
       2. 停止所有 source_workflow_host 进程
            等待超时：max(35s, POST_ALERT_DURATION + 10s)
            确保录制中的告警视频写完
       3. 停止所有 decoder_worker 进程
            等待超时：5s，超时后 kill
       4. 关闭所有 VideoRingBuffer 和 CompressedVideoRingBuffer
            释放共享内存（unlink）
       5. db.close()
```

强制退出只需在超时等待期间再次发送信号。

---

## 11. 常见问题

### 工作流不运行

1. 检查 `VideoSource.enabled` 和 `Workflow.is_active`（Web UI）
2. 检查 `workflow.log` 确认 WorkflowRunner 是否启动
3. 确认算法脚本和模型文件路径存在

### 解码器无输出（无帧）

1. 检查 `run.log` 中 decoder_worker 子进程的退出码
2. 30秒内无帧自动重启，观察 `run.log` 中是否有 `restarting source` 日志
3. 手动测试流地址：`ffprobe <url>`

### 告警不触发

1. 检查 AlertNode 的 `trigger_condition`（窗口模式/阈值）
2. 确认 `ALERT_SUPPRESSION_DURATION` 冷却期已过
3. 开启 `DETECTION_JSONL_LOG_ENABLED=true` 查看原始检测结果

### 录制文件缺失

1. 确认 `RECORDING_ENABLED=true`
2. 确认 `RECORDING_BUFFER_DURATION ≥ PRE_ALERT_DURATION + POST_ALERT_DURATION`
3. 检查 `VIDEO_SAVE_PATH` 目录写权限

### 启动时 "No module named" 错误

虚拟环境未激活，或未执行 `pip install -r requirements.txt`。

### 端口 5002 被占用

`webapp.py` 默认绑定 5002，修改方式：

```bash
PORT=5003 python app/web/webapp.py
```

---

## 12. 数据库说明

| 环境 | 默认数据库 | 配置方式 |
|------|----------|---------|
| 本地开发 | SQLite，路径 `app/data/db/ba.db` | 自动选择 |
| Docker | PostgreSQL，host=`postgres` | 自动选择 |
| 手动指定 | — | `DB_BACKEND=sqlite` 或 `DB_BACKEND=postgres` |

ORM 使用 Peewee，核心表：`Algorithm`、`VideoSource`、`Workflow`、`WorkflowNode`、`WorkflowConnection`、`Alert`、`MLModel`、`User`。
