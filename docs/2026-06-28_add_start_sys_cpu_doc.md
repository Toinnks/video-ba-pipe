# Add CPU Local Startup Document

Date: 2026-06-28

## 目标

新增一份面向 Windows 本地 CPU 环境的系统启动文档，记录使用 conda 环境 `video-sys` 启动后端 worker、后端 API 和前端 dev server 的完整过程。

## 修改文件列表

* docs/start-sys-cpu.md
* docs/2026-06-28_add_start_sys_cpu_doc.md

## 修改内容说明

### 文件：docs/start-sys-cpu.md

* 修改点：新增 CPU 本地启动说明，覆盖环境前提、启动前检查、数据库初始化、worker/API/前端启动、服务验证、日志查看、停止服务和常见问题。
* 修改点：记录 Windows 本地环境中的关键处理方式，包括直接调用 `video-sys` 环境 Python、使用 `npm.cmd`、通过任务计划程序后台运行服务、前端直接调用 `@umijs/max` CLI。

### 文件：docs/2026-06-28_add_start_sys_cpu_doc.md

* 修改点：新增本次文档变更记录，说明新增文档的目标、文件范围、修改内容和验证方式。

## 修改原因

原有启动说明分散在 README 和启动手册中，偏通用部署说明。实际在 Windows 本地 CPU 环境启动时，还需要处理 conda 输出编码、PowerShell npm 执行策略、前端依赖修复、后台进程启动等细节，因此单独沉淀一份可执行的本地启动文档。

## 验证方式

```powershell
Test-Path docs\start-sys-cpu.md
Test-Path docs\2026-06-28_add_start_sys_cpu_doc.md
Get-Content docs\start-sys-cpu.md -TotalCount 20
```
