# 宝塔 Docker 部署 AgentChat

目标服务器：`119.29.55.241`
部署域名：`agent.xxqcloud.cn`

这份流程采用“本地打包前端，服务器只运行静态文件”的方式，避免 4C4G 服务器在宝塔里执行 `npm install` / `npm run build`。

## 1. 本地准备前端产物

在项目根目录执行：

```powershell
cd src/frontend
npm ci
npm run build
cd ../..
```

确认生成目录存在：

```powershell
Test-Path src/frontend/dist/index.html
```

如果返回 `True`，说明前端已经打包好。

## 2. 上传项目到服务器

推荐上传到：

```text
/www/wwwroot/agentchat
```

需要上传的内容至少包括：

```text
docker/
src/backend/
src/frontend/dist/
requirements.txt
.dockerignore
```

如果你用 Git 拉取项目，也可以先拉完整仓库，再把本地生成的 `src/frontend/dist` 上传覆盖到服务器对应目录。

## 3. 准备生产配置

进入服务器项目目录：

```bash
cd /www/wwwroot/agentchat/docker
cp config.production.example.yaml config.yaml
```

编辑 `docker/config.yaml`，至少改这几处：

```yaml
mysql:
  endpoint: "mysql+pymysql://agentchat_user:你的数据库密码@mysql:3306/agentchat"
  async_endpoint: "mysql+aiomysql://agentchat_user:你的数据库密码@mysql:3306/agentchat"

redis:
  endpoint: "redis://redis:6379"
```

同时填写 `multi_models` 里的模型 Key。当前 Compose 已包含 Elasticsearch，知识库会启用关键词检索：

```yaml
rag:
  enable_elasticsearch: true
  vector_db:
    mode: "chroma"
```

4C4G 同机跑 Elasticsearch 会比较紧，当前配置已把 ES JVM 限制为 512M，并把 MySQL/Redis 也压低了内存占用。不要再同机加 Milvus。

## 4. 准备 Docker 环境变量

在 `docker` 目录创建 `.env`：

```bash
MYSQL_ROOT_PASSWORD=改成强密码
MYSQL_PASSWORD=改成和 config.yaml 里一致的密码
```

`MYSQL_PASSWORD` 必须和 `config.yaml` 中 `agentchat_user` 的密码一致。

## 5. 在宝塔启动 Docker Compose

宝塔面板路径：

```text
Docker -> Compose -> 添加 Compose 项目
```

建议填写：

```text
项目名称：agentchat
项目路径：/www/wwwroot/agentchat/docker
Compose 文件：/www/wwwroot/agentchat/docker/docker-compose.bt.yml
```

然后点击启动。如果宝塔没有自动读取 `.env`，在服务器终端执行：

```bash
cd /www/wwwroot/agentchat/docker
docker compose -f docker-compose.bt.yml up -d --build
```

查看状态：

```bash
docker compose -f docker-compose.bt.yml ps
docker compose -f docker-compose.bt.yml logs -f backend
```

前端容器只绑定本机端口：

```text
127.0.0.1:18090 -> 容器 8090
```

## 6. 宝塔添加站点和反向代理

在宝塔：

```text
网站 -> 添加站点
```

填写：

```text
域名：agent.xxqcloud.cn
根目录：可用默认目录，不需要放前端文件
PHP：纯静态或不启用 PHP
```

然后进入该站点：

```text
设置 -> 反向代理 -> 添加反向代理
```

填写：

```text
代理名称：agentchat
目标 URL：http://127.0.0.1:18090
发送域名：$host
```

开启代理后，宝塔的站点 Nginx 会把 `https://agent.xxqcloud.cn` 转到前端容器，前端容器内的 Nginx 再把 `/api/` 转给后端容器。

## 7. 域名解析和 SSL

在 DNS 控制台添加：

```text
类型：A
主机记录：agent
记录值：119.29.55.241
```

等解析生效后，在宝塔站点里申请 SSL：

```text
网站 -> agent.xxqcloud.cn -> SSL -> Let's Encrypt
```

申请成功后开启：

```text
强制 HTTPS
```

## 8. 放行端口

公网只需要开放：

```text
80
443
```

`18090` 只绑定 `127.0.0.1`，不需要公网放行。MySQL 和 Redis 没有映射到宿主机端口，也不应公网开放。

## 9. 验证

浏览器访问：

```text
https://agent.xxqcloud.cn
```

服务器上验证：

```bash
curl http://127.0.0.1:18090/health
curl http://127.0.0.1:18090/api/v1/user/icons
```

如果页面能打开但接口失败，优先检查：

```bash
docker compose -f /www/wwwroot/agentchat/docker/docker-compose.bt.yml logs -f backend
docker compose -f /www/wwwroot/agentchat/docker/docker-compose.bt.yml logs -f frontend
```

## 10. 更新版本

本地重新打包：

```powershell
cd src/frontend
npm run build
cd ../..
```

上传新的代码和 `src/frontend/dist` 后，在服务器执行：

```bash
cd /www/wwwroot/agentchat/docker
docker compose -f docker-compose.bt.yml up -d --build
```

只改后端配置时不需要重新构建：

```bash
docker compose -f docker-compose.bt.yml restart backend
```
