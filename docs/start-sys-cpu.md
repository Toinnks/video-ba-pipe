# CPU 本地启动视频分析系统

本文档记录在 Windows 本地使用 conda 环境 `video-sys` 启动视频分析系统的过程。该方式适用于 CPU 本地开发和验证，不依赖 Docker。

## 目录

- 环境前提
- 启动前检查
- 初始化数据库
- 启动后端 worker
- 启动后端 API
- 启动前端
- 验证服务
- 查看日志
- 停止服务
- 常见问题

## 环境前提

项目目录：

```powershell
D:\projects\pythonProjects\video-ba-pipe
```

Python conda 环境：

```powershell
video-sys
```

前端依赖目录：

```powershell
D:\projects\pythonProjects\video-ba-pipe\frontend\node_modules
```

默认端口：

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://localhost:8000` |
| 后端 API | `http://localhost:5002` |

## 启动前检查

进入项目根目录：

```powershell
cd D:\projects\pythonProjects\video-ba-pipe
```

确认 conda 环境存在：

```powershell
conda env list
```

确认端口未被占用：

```powershell
Get-NetTCPConnection -LocalPort 5002,8000 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,State,OwningProcess
```

确认前端依赖已安装：

```powershell
Test-Path frontend\node_modules
```

如果前端依赖不完整，执行：

```powershell
cd D:\projects\pythonProjects\video-ba-pipe\frontend
npm.cmd install
```

说明：在部分 Windows PowerShell 环境中，直接执行 `npm install` 可能会被执行策略拦截，使用 `npm.cmd install` 更稳定。

## 初始化数据库

推荐直接使用 conda 环境中的 Python 可执行文件，避免 `conda run` 在 GBK 控制台中因为中文输出编码报错：

```powershell
cd D:\projects\pythonProjects\video-ba-pipe
D:\softwareCode\anaconda\envs\video-sys\python.exe -m app.setup_database
```

成功时会看到类似输出：

```text
数据库已使用 Peewee 模型初始化。
```

本地默认使用 SQLite，数据库文件位于：

```text
app/data/db/ba.db
```

## 启动后端 worker

worker 负责视频源和工作流编排执行。

前台启动方式：

```powershell
cd D:\projects\pythonProjects\video-ba-pipe
D:\softwareCode\anaconda\envs\video-sys\python.exe -m app.main
```

后台启动方式可以使用 Windows 任务计划程序。先准备临时启动脚本：

```powershell
$tmp = Join-Path $env:TEMP "video-ba-pipe-runners"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

@'
import os
import sys

ROOT = r"D:\projects\pythonProjects\video-ba-pipe"
LOG_DIR = os.path.join(ROOT, "app", "data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

sys.stdout = open(os.path.join(LOG_DIR, "worker.stdout.log"), "a", encoding="utf-8", buffering=1)
sys.stderr = open(os.path.join(LOG_DIR, "worker.stderr.log"), "a", encoding="utf-8", buffering=1)

os.chdir(ROOT)
sys.path.insert(0, ROOT)

from app.setup_database import setup_database
from app.core.orchestrator import Orchestrator

setup_database()
Orchestrator().run()
'@ | Set-Content -LiteralPath (Join-Path $tmp "run_worker.py") -Encoding UTF8

@"
@echo off
cd /d D:\projects\pythonProjects\video-ba-pipe
D:\softwareCode\anaconda\envs\video-sys\python.exe C:\Users\sgy\AppData\Local\Temp\video-ba-pipe-runners\run_worker.py
"@ | Set-Content -LiteralPath (Join-Path $tmp "run_worker.cmd") -Encoding ASCII
```

创建并运行任务：

```powershell
$start = (Get-Date).AddMinutes(1).ToString('HH:mm')
schtasks /Create /F /TN "video-ba-pipe-worker" /SC ONCE /ST $start /TR "$env:TEMP\video-ba-pipe-runners\run_worker.cmd"
schtasks /Run /TN "video-ba-pipe-worker"
```

## 启动后端 API

API 提供 Web 管理端调用的接口，默认监听 `5002`。

前台启动方式：

```powershell
cd D:\projects\pythonProjects\video-ba-pipe
D:\softwareCode\anaconda\envs\video-sys\python.exe -m app.web.webapp
```

后台启动建议关闭 Flask debug reloader，避免后台进程启动后退出。准备临时启动脚本：

```powershell
$tmp = Join-Path $env:TEMP "video-ba-pipe-runners"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

@'
import os
import sys

ROOT = r"D:\projects\pythonProjects\video-ba-pipe"
LOG_DIR = os.path.join(ROOT, "app", "data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

sys.stdout = open(os.path.join(LOG_DIR, "api.stdout.log"), "a", encoding="utf-8", buffering=1)
sys.stderr = open(os.path.join(LOG_DIR, "api.stderr.log"), "a", encoding="utf-8", buffering=1)

os.chdir(ROOT)
sys.path.insert(0, ROOT)

from app.web.webapp import app

app.run(host="0.0.0.0", port=5002, debug=False, use_reloader=False)
'@ | Set-Content -LiteralPath (Join-Path $tmp "run_api.py") -Encoding UTF8

@"
@echo off
cd /d D:\projects\pythonProjects\video-ba-pipe
D:\softwareCode\anaconda\envs\video-sys\python.exe C:\Users\sgy\AppData\Local\Temp\video-ba-pipe-runners\run_api.py
"@ | Set-Content -LiteralPath (Join-Path $tmp "run_api.cmd") -Encoding ASCII
```

创建并运行任务：

```powershell
$start = (Get-Date).AddMinutes(1).ToString('HH:mm')
schtasks /Create /F /TN "video-ba-pipe-api" /SC ONCE /ST $start /TR "$env:TEMP\video-ba-pipe-runners\run_api.cmd"
schtasks /Run /TN "video-ba-pipe-api"
```

## 启动前端

前台启动方式：

```powershell
cd D:\projects\pythonProjects\video-ba-pipe\frontend
npm.cmd run dev
```

如果任务计划程序中找不到 `max` 命令，直接使用本地安装的 Umi Max CLI：

```powershell
D:\softwareCode\nodejs\node.exe D:\projects\pythonProjects\video-ba-pipe\frontend\node_modules\@umijs\max\bin\max.js dev
```

后台启动脚本：

```powershell
$tmp = Join-Path $env:TEMP "video-ba-pipe-runners"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

@"
@echo off
cd /d D:\projects\pythonProjects\video-ba-pipe\frontend
D:\softwareCode\nodejs\node.exe D:\projects\pythonProjects\video-ba-pipe\frontend\node_modules\@umijs\max\bin\max.js dev >> D:\projects\pythonProjects\video-ba-pipe\app\data\logs\frontend.stdout.log 2>> D:\projects\pythonProjects\video-ba-pipe\app\data\logs\frontend.stderr.log
"@ | Set-Content -LiteralPath (Join-Path $tmp "run_frontend.cmd") -Encoding ASCII
```

创建并运行任务：

```powershell
$start = (Get-Date).AddMinutes(1).ToString('HH:mm')
schtasks /Create /F /TN "video-ba-pipe-frontend" /SC ONCE /ST $start /TR "$env:TEMP\video-ba-pipe-runners\run_frontend.cmd"
schtasks /Run /TN "video-ba-pipe-frontend"
```

启动成功后，前端日志会出现类似信息：

```text
App listening at:
> Local: http://localhost:8000
```

## 验证服务

验证前端：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000 -TimeoutSec 8 |
  Select-Object StatusCode
```

正常返回：

```text
200
```

验证 API 端口：

```powershell
Get-NetTCPConnection -LocalPort 5002 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,State,OwningProcess
```

验证 API 鉴权响应：

```powershell
try {
  Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5002/api/system/info -TimeoutSec 5 |
    Select-Object StatusCode,Content
} catch {
  $_.Exception.Response.StatusCode.value__
}
```

未登录时返回 `401` 属于正常现象，表示 API 已启动且鉴权生效。

验证 worker：

```powershell
Get-Content app\data\logs\worker.stdout.log -Tail 20
```

正常情况下会看到 worker 定期扫描工作流的日志。

## 查看日志

日志路径：

```text
app/data/logs/api.stdout.log
app/data/logs/api.stderr.log
app/data/logs/worker.stdout.log
app/data/logs/worker.stderr.log
app/data/logs/frontend.stdout.log
app/data/logs/frontend.stderr.log
```

查看最近日志：

```powershell
Get-Content app\data\logs\api.stdout.log -Tail 80
Get-Content app\data\logs\worker.stdout.log -Tail 80
Get-Content app\data\logs\frontend.stdout.log -Tail 120
```

## 停止服务

如果使用任务计划程序启动，停止任务：

```powershell
schtasks /End /TN "video-ba-pipe-api"
schtasks /End /TN "video-ba-pipe-worker"
schtasks /End /TN "video-ba-pipe-frontend"
```

如需删除任务：

```powershell
schtasks /Delete /F /TN "video-ba-pipe-api"
schtasks /Delete /F /TN "video-ba-pipe-worker"
schtasks /Delete /F /TN "video-ba-pipe-frontend"
```

## 常见问题

### conda run 出现 UnicodeEncodeError

现象：

```text
UnicodeEncodeError: 'gbk' codec can't encode character
```

处理方式：不要使用 `conda run`，直接调用环境中的 Python：

```powershell
D:\softwareCode\anaconda\envs\video-sys\python.exe -m app.setup_database
```

### PowerShell 无法执行 npm.ps1

现象：

```text
无法加载文件 npm.ps1，因为在此系统上禁止运行脚本
```

处理方式：使用 `npm.cmd`：

```powershell
npm.cmd install
npm.cmd run dev
```

### 前端提示 max 不是内部或外部命令

先修复依赖：

```powershell
cd D:\projects\pythonProjects\video-ba-pipe\frontend
npm.cmd install
```

如果仍然在后台任务中找不到 `max`，直接调用本地 CLI：

```powershell
D:\softwareCode\nodejs\node.exe D:\projects\pythonProjects\video-ba-pipe\frontend\node_modules\@umijs\max\bin\max.js dev
```

### API 返回 401

访问 `/api/system/info` 返回 `401 Unauthorized` 是正常的未登录状态，说明 API 已启动并进入鉴权逻辑。

### worker 日志显示 0 个激活工作流

类似日志：

```text
检测到 0 个激活工作流，分布在 0 个视频源
```

这表示 worker 正常运行，但当前数据库中没有启用的工作流。登录前端后创建并启用视频源、算法和工作流即可。
