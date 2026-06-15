# Video BA Pipe 启动手册

## 目录

- [系统概述](#系统概述)
- [环境要求](#环境要求)
- [方式一：Docker 部署（推荐）](#方式一docker-部署推荐)
  - [CPU 版本](#1-cpu-版本)
  - [CUDA/GPU 版本](#2-cudagpu-版本)
  - [RK3588/NPU 版本](#3-rk3588npu-版本)
- [方式二：本地开发运行](#方式二本地开发运行)
- [环境变量配置说明](#环境变量配置说明)
- [访问地址](#访问地址)
- [首次使用流程](#首次使用流程)
- [常用运维命令](#常用运维命令)
- [常见问题排查](#常见问题排查)

---

## 系统概述

本系统由以下几个服务组成：

| 服务 | 说明 | 默认端口 |
|------|------|----------|
| `worker` | 视频解码 + 工作流执行进程（主引擎） | 无 |
| `api` | Flask/Gunicorn Web API | `5002` |
| `frontend` | 前端管理界面（Nginx） | `8080` |
| `postgres` | PostgreSQL 数据库（内置） | `5432`（仅内网） |
| `rabbitmq` | 消息队列（可选，CUDA compose 内置） | `5672` / `15672` |

---

## 环境要求

### Docker 部署

- Docker >= 20.10
- Docker Compose >= 2.0（使用 `docker compose` 命令，非 `docker-compose`）
- 磁盘空间：建议 `/data` 挂载目录预留 **50GB+**（录制视频和告警图片会持续增长）
- 内存：建议 **8GB+**（多路视频 + 录制缓冲区占用较大，见[录制缓冲区内存估算](#录制缓冲区内存估算)）
- CUDA 版本额外需要：NVIDIA 驱动 + NVIDIA Container Toolkit

### 本地开发

- Python 3.10+
- Node.js 18+（前端开发）
- （可选）PostgreSQL 15+

---

## 方式一：Docker 部署（推荐）

### 准备配置文件

```bash
# 克隆仓库后，复制环境变量模板
cp env.example .env
```

根据实际需求修改 `.env`（关键配置见[环境变量配置说明](#环境变量配置说明)）。
**最少需要确认的配置项：**

- 如果不使用 RabbitMQ，将 `RABBITMQ_ENABLED=false`
- 如果需要修改数据库密码，修改 `POSTGRES_PASSWORD` / `DB_PASSWORD`（保持一致）

---

### 1. CPU 版本

适用于：通用 x86/ARM 服务器，无 GPU。

```bash
docker compose -f docker-compose.yml up -d
```

查看启动状态：

```bash
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml logs -f worker
```

---

### 2. CUDA/GPU 版本

适用于：配备 NVIDIA GPU 的服务器，需要 GPU 加速推理。

**前置条件：**

```bash
# 验证 NVIDIA runtime 可用
docker run --rm --runtime=nvidia nvidia/cuda:12.0-base nvidia-smi
```

启动：

```bash
docker compose -f docker-compose.yml.cuda up -d
```

> CUDA compose 中 `api` 和 `worker` 合并为一个 `app` 容器，同时内置了 RabbitMQ 服务。

---

### 3. RK3588/NPU 版本

适用于：RK3588 ARM 开发板（如 Orange Pi 5、NanoPC-T6 等）。

**板端特殊配置（必须）：**

```bash
# 允许容器间转发（iptables=false 环境必须执行，重启后需重新执行）
iptables -P FORWARD ACCEPT
```

启动：

```bash
docker compose -p video-analysis -f docker-compose.yml.rknn up -d
```

查看状态：

```bash
docker compose -p video-analysis -f docker-compose.yml.rknn ps
```

> - `worker` 容器已透传 `/dev/dri`、`/dev/mpp_service`、`/dev/rga`、`/dev/video-dec0` 等硬件设备。
> - `VIDEO_DECODER_TYPE=rk_mpp` 仅在 `worker` 中启用，`api` 保持软解。
> - 详见 `docs/rk_usage_manual.md` 和 `docs/rk3588_docker.md`。

---

### 停止服务

```bash
# CPU 版本
docker compose -f docker-compose.yml down

# 停止并删除数据卷（会清除数据库！）
docker compose -f docker-compose.yml down -v
```

---

## 方式二：本地开发运行

### 后端

```bash
# 1. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 初始化数据库（本地默认使用 SQLite）
python -m app.setup_database

# 4. 终端 1：启动 worker（视频解码 + 工作流引擎）
python -m app.main

# 5. 终端 2：启动 API 服务
python -m app.web.webapp
```

本地运行默认使用 SQLite，数据库文件位于 `app/data/db/ba.db`。
如需连接 PostgreSQL，在 `.env` 中设置 `DB_BACKEND=postgres` 并配置对应连接参数。

### 前端

```bash
cd frontend
npm install
npm run dev
```

开发环境前端访问：`http://localhost:8000`

### 数据库迁移（SQLite → PostgreSQL）

```bash
# 本地执行
python scripts/migrate_sqlite_to_postgres.py --sqlite-path ./app/data/db/ba.db

# 在 compose 容器内执行（推荐，避免网络问题）
docker compose run --rm -v ./data:/data api python /app/scripts/migrate_sqlite_to_postgres.py --sqlite-path /data/db/ba.db
```

---

## 环境变量配置说明

完整示例见 `env.example`，以下为关键配置分组说明。

### 数据库

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DB_BACKEND` | `sqlite`（本地）/ `postgres`（Docker） | 数据库类型，自动推断 |
| `DB_HOST` | `localhost` | PostgreSQL 地址 |
| `DB_PORT` | `5432` | PostgreSQL 端口 |
| `DB_NAME` | `video_ba_pipe` | 数据库名 |
| `DB_USER` | `video_ba_pipe` | 数据库用户 |
| `DB_PASSWORD` | `video_ba_pipe` | 数据库密码 |

### 解码器

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VIDEO_DECODER_TYPE` | `ffmpeg_sw` | 解码器类型：`ffmpeg_sw` / `nvdec` / `rk_mpp` |
| `VIDEO_FRAME_PIXEL_FORMAT` | `nv12` | 管线帧格式：`nv12` / `rgb24` / `bgr24` |
| `FFMPEG_SW_DECODER_THREADS` | `1` | 软解线程数，多路并发建议保持 1 |
| `DECODER_OUTPUT_QUEUE_SIZE` | `5` | 解码输出队列深度 |
| `IS_EXTREME_DECODE_MODE` | `false` | 极速模式：丢弃中间帧，只取最新帧 |

### 录制缓冲区（影响内存占用）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PRE_ALERT_DURATION` | `30` | 预警前录制时长（秒） |
| `POST_ALERT_DURATION` | `30` | 预警后录制时长（秒） |
| `RECORDING_BUFFER_DURATION` | `62` | 录制缓冲区时长，须 ≥ PRE + POST |
| `RECORDING_FPS` | `10` | 录制视频帧率 |
| `RECORDING_JPEG_QUALITY` | `85` | 缓冲区帧 JPEG 压缩质量 |
| `ANALYSIS_TARGET_FPS` | `3` | 分析工作流采样帧率 |
| `ANALYSIS_BUFFER_SECONDS` | `5` | 分析缓冲区时长（秒） |

#### 录制缓冲区内存估算

> 内存占用（MB） ≈ 帧大小(MB) × RECORDING_FPS × RECORDING_BUFFER_DURATION
>
> 1920×1080 NV12 单帧约 3MB（压缩后约 50-150KB，取决于 JPEG 质量）

| 场景 | 配置 | 估算内存（每路） |
|------|------|-----------------|
| 资源受限 | FPS=5, 时长=42s | ~1.3 GB |
| 推荐（标准监控） | FPS=10, 时长=62s | ~3.7 GB |
| 高质量 | FPS=15, 时长=92s | ~8.2 GB |

### 告警

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ALERT_SUPPRESSION_DURATION` | `60` | 同类告警冷却时长（秒） |
| `ALERT_IMAGE_CLEANUP_ENABLED` | `false` | 是否自动清理旧告警图片 |
| `ALERT_IMAGE_RETENTION_DAYS` | `7` | 告警图片保留天数 |
| `ALERT_IMAGE_MIN_FREE_GB` | `2` | 磁盘剩余低于此值时触发清理（GB） |

### RabbitMQ（可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RABBITMQ_ENABLED` | `false` | 是否启用消息队列 |
| `RABBITMQ_HOST` | `localhost` | RabbitMQ 地址 |
| `RABBITMQ_PORT` | `5672` | RabbitMQ 端口 |
| `RABBITMQ_USER` | `guest` | 用户名 |
| `RABBITMQ_PASSWORD` | `guest` | 密码 |

> 消息格式与接入说明详见 `docs/rabbitmq_integration.md`。

---

## 访问地址

| 服务 | 地址 |
|------|------|
| 前端管理界面 | `http://localhost:8080` |
| 后端 API | `http://localhost:5002` |
| RabbitMQ 管理台（CUDA compose） | `http://localhost:15672`（admin / admin123） |

---

## 首次使用流程

系统启动后，按以下顺序完成初始配置：

**1. 上传 AI 模型**

进入 `管理 → 模型管理`，上传 YOLO 模型文件（`.pt` / `.onnx` / `.rknn`）。

**2. 创建算法**

进入 `管理 → 算法管理`，创建算法并关联模型。
可使用内置脚本模板（`app/user_scripts/templates/`），也可上传自定义脚本。

**3. 添加视频源**

进入 `管理 → 视频源管理`，填写 RTSP/HTTP/本地文件路径，配置解码分辨率和帧率。

**4. 创建工作流**

进入 `管理 → 工作流管理`，在可视化编辑器中：
- 添加 **Source 节点**（选择视频源）
- 添加 **Algorithm 节点**（选择算法），根据需要配置 ROI 区域
- 添加 **Alert 节点**（配置告警级别、时间窗口检测、告警抑制）
- 连接各节点，激活工作流

**5. 查看告警**

进入 `告警记录` 查看触发的告警，包含告警图片和录制视频。

---

## 常用运维命令

```bash
# 查看所有容器状态
docker compose -f docker-compose.yml ps

# 实时查看 worker 日志
docker compose -f docker-compose.yml logs -f worker

# 实时查看 api 日志
docker compose -f docker-compose.yml logs -f api

# 过滤关键日志
docker compose -f docker-compose.yml logs worker | grep -E "(ERROR|WorkflowWorker|Orchestrator)"

# 进入 worker 容器排障
docker compose -f docker-compose.yml exec worker bash

# 重启单个服务
docker compose -f docker-compose.yml restart worker

# 拉取最新镜像并重启
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
```

---

## 常见问题排查

### worker 启动后无工作流运行

- 确认已在 Web UI 中激活工作流（工作流状态为"启用"）
- 检查工作流是否正确连接了 Source 节点和 Algorithm 节点
- 查看 worker 日志：`docker compose logs worker | grep -i "workflow"`

### 视频源无法连接

- 确认 RTSP/HTTP URL 在宿主机网络中可访问
- Docker 容器内访问宿主机服务需用宿主机 IP（不能用 `localhost`）
- 检查防火墙规则，确保容器可以访问视频源地址

### 无告警图片/视频生成

- 确认 `RECORDING_ENABLED=true`
- 检查 `VIDEO_SAVE_PATH` 和 `FRAME_SAVE_PATH` 目录是否有写权限
- 确认 `RECORDING_BUFFER_DURATION >= PRE_ALERT_DURATION + POST_ALERT_DURATION`

### 内存持续增长

- 减小 `RECORDING_BUFFER_DURATION` / `RECORDING_FPS`
- 减少并发视频源数量，或降低 `ANALYSIS_BUFFER_SECONDS`
- 开启 `IS_EXTREME_DECODE_MODE=true`（跳过中间帧）

### RK3588 容器间网络不通

参见[RK3588/NPU 版本](#3-rk3588npu-版本)中的前置配置，必须执行：

```bash
iptables -P FORWARD ACCEPT
```

若重启后失效，可将该命令加入 `/etc/rc.local` 或 systemd 服务实现持久化。

### 算法脚本不加载

- 确认脚本路径在数据库中配置正确（或 `USER_SCRIPTS_ROOT` 挂载正确）
- 检查脚本是否包含 `SCRIPT_METADATA`、`init()`、`process()` 三个必要元素
- 查看 worker 日志中的脚本加载错误信息

### 开启检测结果调试日志

```bash
# 在 .env 中设置后重启 worker
DETECTION_JSONL_LOG_ENABLED=true
```

日志写入 `logs/detection_results_YYYYMMDD.jsonl`，可用于对比不同环境（x86/RKNN）的推理输出差异。
