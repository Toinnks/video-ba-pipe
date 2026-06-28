# RK3588 镜像构建与 GitHub Actions 流程

本文档说明将代码推送到 GitHub 后，如何基于当前源码构建 RK3588 开发板可用的 `linux/arm64` 镜像，并说明现有 workflow 如何使用，以及如果需要自动构建 RK 镜像应该怎么修改。

## 当前结论

当前仓库已经有 RK3588 镜像构建 workflow，不需要从零新增 workflow。

相关文件：

| 文件 | 作用 |
| --- | --- |
| `.github/workflows/build_ffmpeg_rk.yml` | 构建 RK3588 FFmpeg 基础镜像 |
| `.github/workflows/build_backend_images.yml` | 构建后端镜像，手动选择 `runtime=rk` 可构建 RK 后端 |
| `.github/workflows/build_frontend_images.yml` | 构建前端镜像，选择 `linux/arm64` 可构建 RK 前端 |
| `Dockerfile.ffmpeg.rk` | RK FFmpeg 基础镜像 Dockerfile |
| `Dockerfile.rk` | RK 后端业务镜像 Dockerfile |
| `frontend/Dockerfile.rk` | RK 前端 Nginx 镜像 Dockerfile |
| `docker-compose.yml.rknn` | RK3588 开发板部署 compose |

RK3588 需要的镜像关系：

```text
ghcr.io/<owner>/video-ba-pipe-ffmpeg-rk:rkmpp
        |
        | Dockerfile.rk 通过 FFMPEG_RK_IMAGE 复用 /opt/ffmpeg
        v
ghcr.io/<owner>/<repo>:rk

ghcr.io/<owner>/<repo>-frontend:rk
```

## 推送代码到 GitHub

先确认本地变更：

```bash
git status
```

提交代码：

```bash
git add .
git commit -m "prepare rk3588 image build"
```

推送到 GitHub：

```bash
git push origin main
```

说明：

- 现有后端 workflow 在 `push main` 时默认只自动构建 CPU 后端镜像。
- RK 后端镜像默认需要手动触发 `Build backend images` 并选择 `runtime=rk`。
- 前端 workflow 在 `push main` 且 `frontend/**` 有变化时会自动构建 amd64 和 arm64 前端镜像，也可以手动触发只构建 `linux/arm64`。

## GitHub Actions 构建顺序

推荐按以下顺序构建：

1. 构建 RK FFmpeg 基础镜像。
2. 构建 RK 后端业务镜像。
3. 构建 RK 前端镜像。

### 1. 构建 RK FFmpeg 基础镜像

进入 GitHub 仓库页面：

```text
Actions -> Build and publish RK3588 FFmpeg image -> Run workflow
```

参数建议：

| 参数 | 建议值 | 说明 |
| --- | --- | --- |
| `image_name` | `video-ba-pipe-ffmpeg-rk` | 一般保持默认 |
| `tag` | `rkmpp` | 一般保持默认 |
| `ffmpeg_rk_package` | 留空 | 留空时使用仓库内 `vendor/ffmpeg/ffmpeg-rk3588-rkmpp.tar.gz` |

产物：

```text
ghcr.io/<owner>/video-ba-pipe-ffmpeg-rk:rkmpp
ghcr.io/<owner>/video-ba-pipe-ffmpeg-rk:sha-<commit>
```

### 2. 构建 RK 后端业务镜像

进入 GitHub 仓库页面：

```text
Actions -> Build backend images -> Run workflow
```

参数建议：

| 参数 | 建议值 | 说明 |
| --- | --- | --- |
| `runtime` | `rk` | 只构建 RK3588 后端 |
| `torch_whl` | 留空 | 如需预装 ARM64 PyTorch wheel 再填写 URL |
| `onnxruntime_whl` | 留空 | 如需预装 ARM64 ONNX Runtime wheel 再填写 URL |
| `rknn_toolkit_lite2_whl` | 留空 | 留空时使用 `vendor/rknn_wheels/rknn_toolkit_lite2-*.whl` |
| `ffmpeg_rk_image` | 留空 | 留空时默认使用 `ghcr.io/<owner>/video-ba-pipe-ffmpeg-rk:rkmpp` |

产物：

```text
ghcr.io/<owner>/<repo>:rk
ghcr.io/<owner>/<repo>:rk-<commit>
```

其中：

- `<owner>` 是 GitHub 用户名或组织名，会被 workflow 转成小写。
- `<repo>` 是仓库名，会被 workflow 转成小写。

### 3. 构建 RK 前端镜像

进入 GitHub 仓库页面：

```text
Actions -> Build frontend images -> Run workflow
```

参数建议：

| 参数 | 建议值 | 说明 |
| --- | --- | --- |
| `platform` | `linux/arm64` | RK3588 是 ARM64 |

产物：

```text
ghcr.io/<owner>/<repo>-frontend:rk
ghcr.io/<owner>/<repo>-frontend:rk-<commit>
```

## GHCR 权限检查

GitHub Actions 推送 GHCR 需要 workflow 有 `packages: write` 权限。当前三个 workflow 的 job 中已经配置：

```yaml
permissions:
  contents: read
  packages: write
```

如果构建成功但推送失败，检查仓库设置：

```text
Settings -> Actions -> General -> Workflow permissions
```

建议选择：

```text
Read and write permissions
```

如果镜像是私有包，RK3588 设备拉取前需要登录：

```bash
echo "<github_pat>" | docker login ghcr.io -u <github_username> --password-stdin
```

PAT 至少需要 `read:packages` 权限；如果本地也要推送镜像，需要 `write:packages`。

## 是否需要修改 workflow

如果接受“RK 镜像手动构建”，当前 workflow 不需要修改。

如果希望每次 push 到 `main` 后自动构建 RK 后端，需要修改 `.github/workflows/build_backend_images.yml`。

### 修改点 1：push paths 加入 RK 相关文件

当前 `build_backend_images.yml` 的 `push.paths` 没有包含 `Dockerfile.rk`、`Dockerfile.ffmpeg.rk` 和 vendor RK 资源。建议改成：

```yaml
on:
  push:
    branches: ["main"]
    paths:
      - "app/**"
      - "scripts/**"
      - "requirements.txt"
      - "Dockerfile.cpu"
      - "Dockerfile.rk"
      - "Dockerfile.ffmpeg.rk"
      - "vendor/rknn_wheels/**"
      - "vendor/ffmpeg/**"
      - ".github/workflows/build_backend_images.yml"
```

说明：

- `Dockerfile.rk` 变化会影响 RK 后端镜像。
- `vendor/rknn_wheels/**` 变化会影响 RKNNLite Python 包。
- `vendor/ffmpeg/**` 变化会影响 FFmpeg 基础镜像，但后端 RK 镜像仍依赖已发布的 `FFMPEG_RK_IMAGE`。

### 修改点 2：允许 push main 自动跑 build-rk

当前 `build-rk` job 条件是：

```yaml
if: inputs.runtime == 'rk' || inputs.runtime == 'all'
```

这意味着 push 事件不会构建 RK 后端。要让 push main 也构建 RK 后端，可改为：

```yaml
if: github.event_name == 'push' || inputs.runtime == 'rk' || inputs.runtime == 'all'
```

注意：这样每次命中 `push.paths` 都会通过 QEMU 构建 ARM64 后端，耗时会明显增加。

### 修改点 3：是否自动构建 FFmpeg 基础镜像

当前 `.github/workflows/build_ffmpeg_rk.yml` 只支持 `workflow_dispatch`，也就是手动触发。

如果希望 `vendor/ffmpeg/**` 或 `Dockerfile.ffmpeg.rk` 变化后自动构建 FFmpeg 基础镜像，可以加上：

```yaml
on:
  push:
    branches: ["main"]
    paths:
      - "Dockerfile.ffmpeg.rk"
      - "vendor/ffmpeg/**"
      - ".github/workflows/build_ffmpeg_rk.yml"
  workflow_dispatch:
    inputs:
      image_name:
        description: 'Container image name'
        required: false
        default: 'video-ba-pipe-ffmpeg-rk'
        type: string
      tag:
        description: 'Docker image tag'
        required: false
        default: 'rkmpp'
        type: string
      ffmpeg_rk_package:
        description: 'Optional prebuilt ffmpeg package URL for RK/rkmpp (leave empty to use vendored package or Debian ffmpeg fallback)'
        required: false
        default: ''
        type: string
```

但如果自动构建 FFmpeg 基础镜像，`github.event.inputs.*` 在 push 事件中不存在，后续引用要兼容 push。建议把 metadata 参数改成带默认值的环境变量：

```yaml
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.image_name || 'video-ba-pipe-ffmpeg-rk' }}
  IMAGE_TAG: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.tag || 'rkmpp' }}
  FFMPEG_RK_PACKAGE: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.ffmpeg_rk_package || '' }}
```

然后把原来的引用：

```yaml
images: ${{ env.REGISTRY }}/${{ env.REPO_OWNER }}/${{ github.event.inputs.image_name }}
type=raw,value=${{ github.event.inputs.tag }}
FFMPEG_RK_PACKAGE=${{ github.event.inputs.ffmpeg_rk_package }}
```

改成：

```yaml
images: ${{ env.REGISTRY }}/${{ env.REPO_OWNER }}/${{ env.IMAGE_NAME }}
type=raw,value=${{ env.IMAGE_TAG }}
FFMPEG_RK_PACKAGE=${{ env.FFMPEG_RK_PACKAGE }}
```

### 修改点 4：前端 workflow 通常不需要改

`.github/workflows/build_frontend_images.yml` 中的 RK job 条件已经包含 push：

```yaml
if: github.event_name == 'push' || inputs.platform == 'linux/arm64' || inputs.platform == 'all'
```

因此当 `frontend/**` 变更并 push 到 `main` 时，前端会自动构建：

```text
ghcr.io/<owner>/<repo>-frontend:rk
```

如果只想手动构建 RK 前端，可以把 RK job 条件改成：

```yaml
if: inputs.platform == 'linux/arm64' || inputs.platform == 'all'
```

## 本地构建并推送 RK 镜像

如果不使用 GitHub Actions，也可以本地构建 ARM64 镜像并推送。

准备 buildx：

```bash
docker run --privileged --rm tonistiigi/binfmt --install arm64
docker buildx create --use --name multiarch-builder
docker buildx inspect --bootstrap
```

登录 GHCR：

```bash
echo "<github_pat>" | docker login ghcr.io -u <github_username> --password-stdin
```

设置变量：

```bash
OWNER=<github_owner_lowercase>
REPO=<repo_name_lowercase>
REGISTRY=ghcr.io/${OWNER}
```

构建并推送 FFmpeg 基础镜像：

```bash
docker buildx build \
  --platform linux/arm64 \
  -f Dockerfile.ffmpeg.rk \
  -t ${REGISTRY}/video-ba-pipe-ffmpeg-rk:rkmpp \
  --push \
  .
```

构建并推送 RK 后端镜像：

```bash
docker buildx build \
  --platform linux/arm64 \
  -f Dockerfile.rk \
  --build-arg FFMPEG_RK_IMAGE=${REGISTRY}/video-ba-pipe-ffmpeg-rk:rkmpp \
  -t ${REGISTRY}/${REPO}:rk \
  --push \
  .
```

构建并推送 RK 前端镜像：

```bash
docker buildx build \
  --platform linux/arm64 \
  -f frontend/Dockerfile.rk \
  -t ${REGISTRY}/${REPO}-frontend:rk \
  --push \
  ./frontend
```

## RK3588 开发板部署

在 RK3588 开发板上登录镜像仓库：

```bash
echo "<github_pat>" | docker login ghcr.io -u <github_username> --password-stdin
```

修改 `docker-compose.yml.rknn` 中的镜像地址。

当前示例：

```yaml
image: ghcr.io/zuoa/video-ba-pipe:rk
image: ghcr.io/zuoa/video-ba-pipe-frontend:rk
```

改成你的仓库地址：

```yaml
image: ghcr.io/<owner>/<repo>:rk
image: ghcr.io/<owner>/<repo>-frontend:rk
```

准备 `.env`：

```bash
cp env.example .env
```

如果开发板 Docker 网络转发异常，先执行：

```bash
sudo iptables -P FORWARD ACCEPT
```

拉取并启动：

```bash
docker compose -f docker-compose.yml.rknn pull
docker compose -f docker-compose.yml.rknn up -d
docker compose -f docker-compose.yml.rknn ps
```

查看日志：

```bash
docker compose -f docker-compose.yml.rknn logs -f api
docker compose -f docker-compose.yml.rknn logs -f worker
docker compose -f docker-compose.yml.rknn logs -f frontend
```

访问：

```text
http://<rk3588-device-ip>:8080
```

## RK3588 运行前检查

开发板上需要存在这些硬件设备节点：

```bash
ls -la /dev/dri /dev/mpp_service /dev/rga /dev/video-dec0 /dev/video-enc0
```

需要挂载 RKNN runtime：

```text
/opt/rknn:/opt/rknn:ro
```

容器内需要能找到：

```text
/opt/rknn/lib/librknnrt.so
```

`docker-compose.yml.rknn` 中 worker 已经设置：

```yaml
VIDEO_DECODER_TYPE=rk_mpp
LD_LIBRARY_PATH=/opt/ffmpeg/lib:/opt/ffmpeg/lib64:/opt/rknn/lib:/usr/local/lib:/usr/lib/aarch64-linux-gnu
```

## 构建失败排查

### 找不到 RKNN wheel

确认仓库内存在：

```text
vendor/rknn_wheels/rknn_toolkit_lite2-*.whl
```

当前 RK 后端镜像使用 Python 3.11，因此 wheel 需要匹配 `cp311` 和 `linux_aarch64`。

### 找不到 FFmpeg RK 包

确认仓库内存在：

```text
vendor/ffmpeg/ffmpeg-rk3588-rkmpp.tar.gz
```

或者在 `Build and publish RK3588 FFmpeg image` 手动参数中填写 `ffmpeg_rk_package` URL。

### 后端 RK 镜像找不到 FFmpeg 基础镜像

先确认 FFmpeg 基础镜像已经发布：

```bash
docker manifest inspect ghcr.io/<owner>/video-ba-pipe-ffmpeg-rk:rkmpp
```

如果你的基础镜像名称不是默认值，在 `Build backend images` 中显式填写：

```text
ffmpeg_rk_image=ghcr.io/<owner>/<custom-ffmpeg-image>:<tag>
```

### 开发板拉取 GHCR 镜像失败

检查：

1. 开发板能访问 `ghcr.io`。
2. 私有镜像已执行 `docker login ghcr.io`。
3. 镜像 owner 和 repo 名全部小写。
4. tag 是否存在，例如 `rk`、`rk-<commit>`、`rkmpp`。

### worker 无法使用 NPU 或硬解

检查设备节点：

```bash
ls -la /dev/dri /dev/mpp_service /dev/rga
```

检查容器内 FFmpeg 是否带 rkmpp：

```bash
docker compose -f docker-compose.yml.rknn exec worker ffmpeg -decoders | grep rkmpp
```

检查 RKNN runtime：

```bash
docker compose -f docker-compose.yml.rknn exec worker ls -la /opt/rknn/lib
```
