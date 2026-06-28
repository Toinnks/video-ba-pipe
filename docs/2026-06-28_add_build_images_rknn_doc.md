# Add RK3588 Image Build Document

Date: 2026-06-28

## 目标

新增 RK3588 镜像构建文档，说明代码推送到 GitHub 后如何使用现有 GitHub Actions 基于源码构建 RKNN/RK3588 所需的 ARM64 镜像，并说明 workflow 在需要自动构建 RK 镜像时应如何调整。

## 修改文件列表

* docs/build-images-rknn.md
* docs/2026-06-28_add_build_images_rknn_doc.md

## 修改内容说明

### 文件：docs/build-images-rknn.md

* 修改点：新增 RK3588 镜像构建流程，覆盖代码推送、GitHub Actions 构建顺序、GHCR 权限、RK 后端/前端/FFmpeg 基础镜像产物和 RK3588 开发板部署。
* 修改点：基于现有 `.github/workflows/build_ffmpeg_rk.yml`、`.github/workflows/build_backend_images.yml`、`.github/workflows/build_frontend_images.yml` 说明当前 workflow 的行为。
* 修改点：提供可选 workflow 修改片段，包括 push 自动构建 RK 后端、自动构建 FFmpeg 基础镜像、前端 RK 自动构建策略调整。

### 文件：docs/2026-06-28_add_build_images_rknn_doc.md

* 修改点：新增本次文档变更记录，说明新增文档的目标、范围、内容和验证方式。

## 修改原因

已有文档分别说明了 Docker 构建维度、RK3588 Docker 构建和发布指南，但缺少一份直接面向“推送 GitHub 后基于源码构建 RK3588 镜像，并参考现有 workflow 判断怎么改”的操作说明。新增独立文档便于后续 CI 配置和 RK3588 部署复用。

## 验证方式

```powershell
Test-Path docs\build-images-rknn.md
Test-Path docs\2026-06-28_add_build_images_rknn_doc.md
Get-Content docs\build-images-rknn.md -TotalCount 20
```
