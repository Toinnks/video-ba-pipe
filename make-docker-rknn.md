# RK3588 镜像构建与发布指南

本文说明如何将本项目打包成 RK3588（RKNN/MPP）运行版本的 Docker 镜像，推送到镜像仓库，并在 RK3588 设备上拉取部署。

---

## 镜像构成

RK3588 版本共需要三个镜像，有依赖顺序：

```
[1] video-ba-pipe-ffmpeg-rk:rkmpp   ← FFmpeg 基础镜像（含 rkmpp 支持）
         ↓ COPY --from
[2] video-ba-pipe:rk                ← 后端业务镜像（API + Worker）
[3] video-ba-pipe-frontend:rk       ← 前端 Nginx 镜像
```

`Dockerfile.rk` 会从镜像 [1] 复制 `/opt/ffmpeg`，所以镜像 [1] **必须先构建**。

---

## 方式一：GitHub Actions（推荐）

如果代码已推送到 GitHub，直接触发 CI 构建并自动推送到 GHCR（`ghcr.io`）。

### 前提条件

- 代码仓库托管在 GitHub
- 仓库开启了 `packages: write` 权限（Actions 默认有 `GITHUB_TOKEN`，已在 workflow 中配置）
- `vendor/rknn_wheels/` 目录下放置了 `rknn_toolkit_lite2-*.whl`（已有：`rknn_toolkit_lite2-2.0.0b1-cp311-cp311-linux_aarch64.whl`）
- `vendor/ffmpeg/` 目录下放置了 RK3588 专用 FFmpeg 压缩包（已有：`ffmpeg-rk3588-rkmpp.tar.gz`）

### 步骤 1：构建 FFmpeg 基础镜像

进入仓库页面 → **Actions** → `Build and publish RK3588 FFmpeg image` → **Run workflow**

| 参数 | 默认值 | 说明 |
|---|---|---|
| `image_name` | `video-ba-pipe-ffmpeg-rk` | 镜像名，一般不改 |
| `tag` | `rkmpp` | 镜像 tag，一般不改 |
| `ffmpeg_rk_package` | 留空 | 留空则使用 `vendor/ffmpeg/` 下的压缩包 |

构建完成后，镜像会推送到：
```
ghcr.io/<你的用户名>/video-ba-pipe-ffmpeg-rk:rkmpp
```

### 步骤 2：构建后端镜像

进入 **Actions** → `Build backend images` → **Run workflow**

| 参数 | 值 | 说明 |
|---|---|---|
| `runtime` | `rk` | 选择 RK3588 后端 |
| `ffmpeg_rk_image` | 留空 | 留空自动使用步骤 1 推送的镜像 |
| 其他 whl 参数 | 留空 | 使用 vendor 目录下的预置 wheel |

构建完成后：
```
ghcr.io/<你的用户名>/video-ba-pipe:rk
ghcr.io/<你的用户名>/video-ba-pipe:rk-<commit-sha>
```

### 步骤 3：构建前端镜像

进入 **Actions** → `Build frontend images` → **Run workflow**

| 参数 | 值 | 说明 |
|---|---|---|
| `platform` | `linux/arm64` | RK3588 是 ARM64 |

构建完成后：
```
ghcr.io/<你的用户名>/video-ba-pipe-frontend:rk
ghcr.io/<你的用户名>/video-ba-pipe-frontend:rk-<commit-sha>
```

---

## 方式二：本地构建后推送

适用于没有 GitHub 仓库，或者想推送到 Docker Hub / 私有仓库的场景。

### 前提条件

构建机器要求：
- **系统**：Linux（推荐 Ubuntu 22.04）
- **架构**：x86_64（使用 QEMU 跨平台编译 ARM64）或 ARM64 原生设备
- **Docker**：已安装，版本 ≥ 23
- **QEMU**（x86 机器跨编译时必须）：
  ```bash
  docker run --privileged --rm tonistiigi/binfmt --install arm64
  ```
- **Docker Buildx**：
  ```bash
  docker buildx create --use --name multiarch-builder
  docker buildx inspect --bootstrap
  ```

### 推送目标：GHCR（GitHub Container Registry）

```bash
# 登录
echo "<your-github-pat>" | docker login ghcr.io -u <your-github-username> --password-stdin
```

PAT 需要 `write:packages` 权限，在 GitHub Settings → Developer settings → Personal access tokens 中生成。

### 推送目标：Docker Hub

```bash
docker login -u <your-dockerhub-username>
```

### 构建变量说明

后续命令中，将 `REGISTRY` 替换为实际仓库前缀：

| 目标仓库 | REGISTRY 示例 |
|---|---|
| GHCR | `ghcr.io/你的用户名` |
| Docker Hub | `你的用户名` |
| 私有仓库 | `192.168.1.100:5000` |

---

### 第一步：构建并推送 FFmpeg 基础镜像

```bash
REGISTRY=ghcr.io/你的用户名

docker buildx build \
  --platform linux/arm64 \
  -f Dockerfile.ffmpeg.rk \
  -t ${REGISTRY}/video-ba-pipe-ffmpeg-rk:rkmpp \
  --push \
  .
```

> `vendor/ffmpeg/ffmpeg-rk3588-rkmpp.tar.gz` 会在构建时自动被 Dockerfile 复制和使用，无需手动指定。

---

### 第二步：构建并推送后端镜像

```bash
REGISTRY=ghcr.io/你的用户名

docker buildx build \
  --platform linux/arm64 \
  -f Dockerfile.rk \
  --build-arg FFMPEG_RK_IMAGE=${REGISTRY}/video-ba-pipe-ffmpeg-rk:rkmpp \
  -t ${REGISTRY}/video-ba-pipe:rk \
  --push \
  .
```

如果有更新版本的 RKNN toolkit wheel 或 onnxruntime，可通过 `--build-arg` 指定：

```bash
# 可选：指定额外的 wheel（留空则使用 vendor/rknn_wheels/ 下预置的）
--build-arg RKNN_TOOLKIT_LITE2_WHL=""
--build-arg ONNXRUNTIME_WHL=""
--build-arg TORCH_WHL=""
```

---

### 第三步：构建并推送前端镜像

```bash
REGISTRY=ghcr.io/你的用户名

docker buildx build \
  --platform linux/arm64 \
  -f frontend/Dockerfile.rk \
  --build-arg BUILDPLATFORM=linux/amd64 \
  --build-arg TARGETPLATFORM=linux/arm64 \
  -t ${REGISTRY}/video-ba-pipe-frontend:rk \
  --push \
  ./frontend
```

---

### 本地验证（不推送，仅本地加载测试）

如果只想在本地验证镜像构建成功，把 `--push` 换成 `--load`（注意：`--load` 不支持多平台，只能本地同架构验证）：

```bash
# 在 ARM64 机器上本地验证
docker buildx build \
  --platform linux/arm64 \
  -f Dockerfile.rk \
  --build-arg FFMPEG_RK_IMAGE=video-ba-pipe-ffmpeg-rk:rkmpp \
  -t video-ba-pipe:rk \
  --load \
  .
```

---

## 在 RK3588 设备上部署

### 前提条件

RK3588 设备上需要：
- 已安装 Docker（`curl -fsSL https://get.docker.com | sh`）
- 已安装 Docker Compose（`apt install docker-compose-plugin`）
- NPU 运行时库位于 `/opt/rknn/lib/`（通常随 BSP/SDK 安装）
- `/dev/mpp_service`、`/dev/dri`、`/dev/rga` 等设备节点存在

### 第一步：登录镜像仓库（如果是私有仓库）

```bash
# GHCR
echo "<your-github-pat>" | docker login ghcr.io -u <your-github-username> --password-stdin

# Docker Hub（公开镜像可跳过）
docker login -u <your-dockerhub-username>
```

### 第二步：修改 docker-compose.yml.rknn

将 compose 文件中的镜像地址替换为你实际推送的地址：

```yaml
# 修改前（示例占位）
image: ghcr.io/zuoa/video-ba-pipe:rk
image: ghcr.io/zuoa/video-ba-pipe-frontend:rk

# 修改后（替换为你的用户名）
image: ghcr.io/<你的用户名>/video-ba-pipe:rk
image: ghcr.io/<你的用户名>/video-ba-pipe-frontend:rk
```

### 第三步：准备环境变量

```bash
cp env.example .env
# 按需编辑 .env，主要配置：
# - POSTGRES_PASSWORD
# - RABBITMQ_USER / RABBITMQ_PASSWORD（如果启用）
```

### 第四步：拉取并启动

```bash
# 拉取所有镜像
docker compose -f docker-compose.yml.rknn pull

# 后台启动
docker compose -f docker-compose.yml.rknn up -d

# 查看状态
docker compose -f docker-compose.yml.rknn ps

# 查看日志
docker compose -f docker-compose.yml.rknn logs -f worker
docker compose -f docker-compose.yml.rknn logs -f api
```

服务启动后，访问 `http://<设备IP>:8080` 进入 Web 界面。

### 第五步：初始化数据库（首次运行）

```bash
docker compose -f docker-compose.yml.rknn exec api python setup_database.py
```

---

## 常见问题

### 构建时报找不到 rknn wheel

检查 `vendor/rknn_wheels/` 下是否存在 `rknn_toolkit_lite2-*.whl`。当前仓库已包含：
```
vendor/rknn_wheels/rknn_toolkit_lite2-2.0.0b1-cp311-cp311-linux_aarch64.whl
```
该 wheel 只支持 Python 3.11，Dockerfile.rk 已使用 `python:3.11-slim-bookworm` 基础镜像，匹配。

### 构建时报找不到 ffmpeg 包

检查 `vendor/ffmpeg/` 下是否存在 `*.tar.gz` / `*.tgz` / `*.tar.xz` / `*.tar` 文件。当前仓库已包含：
```
vendor/ffmpeg/ffmpeg-rk3588-rkmpp.tar.gz
```

### QEMU 跨平台构建很慢

RK3588 镜像是 ARM64，在 x86 机器上用 QEMU 仿真编译，耗时较长（通常 10~30 分钟）属于正常现象。推荐使用 GitHub Actions 构建，利用 GitHub 提供的 runner 并行完成。

### 设备上拉取镜像失败

1. 确认 RK3588 设备有访问 `ghcr.io` 的网络
2. 如需代理，在 Docker 配置 `/etc/docker/daemon.json` 中配置 registry-mirror 或设置代理
3. 私有仓库需先执行 `docker login`

### worker 容器无法访问 NPU 设备

确认 `/dev/mpp_service` 存在且有权限：
```bash
ls -la /dev/mpp_service /dev/dri /dev/rga /dev/video-dec0
```
如设备节点路径不同，修改 `docker-compose.yml.rknn` 中 `worker.devices` 段。
