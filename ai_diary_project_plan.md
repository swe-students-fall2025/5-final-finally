# AI语音日记系统 - 项目实施方案

> **Course Project MVP版本**  
> 目标：实现语音录制 → AI对话 → 自动生成日记的完整流程  
> 预计工期：2-3周

---

## 📋 目录

1. [项目概述](#项目概述)
2. [技术架构](#技术架构)
3. [数据库设计](#数据库设计)
4. [模块详细设计](#模块详细设计)
5. [API接口规范](#api接口规范)
6. [部署方案](#部署方案)
7. [五人分工方案](#五人分工方案)
8. [开发时间线](#开发时间线)
9. [技术选型说明](#技术选型说明)
10. [注意事项](#注意事项)

---

## 1. 项目概述

### 核心功能
- 用户通过麦克风录音与AI对话
- AI实时回应用户的语音内容
- 对话结束后自动生成日记
- 查看和管理历史日记

### 技术要求
- ✅ 至少2个自定义子系统（Flask App + AI Service）
- ✅ MongoDB数据库
- ✅ Docker容器化部署
- ✅ GitHub Actions CI/CD
- ✅ 单元测试覆盖率 ≥ 80%
- ✅ 部署到Digital Ocean

### 简化原则（MVP）
- ❌ 不实时转录（录完再转）
- ❌ 不存储音频文件（只存文字）
- ❌ 不需要用户认证（简单username标识）
- ❌ 不需要复杂UI（功能优先）

---

## 2. 技术架构

### 2.1 系统架构图

```
┌─────────────────────────────────────────┐
│            用户浏览器                    │
│  ┌─────────────────────────────────┐   │
│  │  前端界面 (HTML/CSS/JS)          │   │
│  │  - 录音控制                      │   │
│  │  - 对话显示                      │   │
│  │  - 日记浏览                      │   │
│  └──────────────┬──────────────────┘   │
└─────────────────┼────────────────────────┘
                  │ HTTP/REST API
                  ↓
┌─────────────────────────────────────────┐
│     Flask App Container (5000端口)       │
│  ┌─────────────────────────────────┐   │
│  │  业务逻辑层                      │   │
│  │  - 用户管理                      │   │
│  │  - 对话管理                      │   │
│  │  - 日记CRUD                      │   │
│  └──────┬────────────────┬─────────┘   │
└─────────┼────────────────┼──────────────┘
          │                │
          │ MongoDB        │ HTTP
          │ Connection     │ Request
          ↓                ↓
┌─────────────────┐  ┌─────────────────────┐
│   MongoDB       │  │  AI Service         │
│   Container     │  │  Container (5001)   │
│                 │  │                     │
│  Collections:   │  │  - Whisper (语音)   │
│  - users        │  │  - Gemini (对话)    │
│  - conversations│  │  - Gemini (日记)    │
│  - diaries      │  │                     │
└─────────────────┘  └─────────────────────┘
```

### 2.2 容器说明

| 容器名称 | 用途 | 端口 | 镜像来源 |
|---------|------|------|---------|
| flask-app | 业务逻辑、API服务 | 5000 | 自定义构建 |
| ai-service | AI处理（转录+对话+生成） | 5001 | 自定义构建 |
| mongodb | 数据存储 | 27017 | 官方镜像 |

---

## 3. 数据库设计

### 3.1 Users Collection

```json
{
  "_id": "ObjectId",
  "username": "john_doe",
  "email": "john@example.com",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**索引：**
- `username`: 唯一索引

### 3.2 Conversations Collection

```json
{
  "_id": "ObjectId",
  "user_id": "ObjectId",
  "date": "2024-01-15",
  "messages": [
    {
      "role": "ai",
      "text": "Hi! How was your day?",
      "timestamp": "2024-01-15T18:30:00Z"
    },
    {
      "role": "user",
      "text": "It was great! I had a productive meeting.",
      "timestamp": "2024-01-15T18:31:00Z"
    }
  ],
  "status": "active",
  "created_at": "2024-01-15T18:30:00Z"
}
```

**索引：**
- `user_id` + `date`: 复合索引
- `status`: 普通索引

**字段说明：**
- `status`: "active"（进行中）或 "completed"（已完成）
- `messages`: 完整对话历史

### 3.3 Diaries Collection

```json
{
  "_id": "ObjectId",
  "user_id": "ObjectId",
  "conversation_id": "ObjectId",
  "date": "2024-01-15",
  "title": "A Productive Monday",
  "content": "Today was an amazing day. I had a productive meeting...",
  "created_at": "2024-01-15T18:50:00Z"
}
```

**索引：**
- `user_id` + `date`: 复合索引

---

## 4. 模块详细设计

### 4.1 Flask App 模块

#### 文件结构
```
flask-app/
├── Dockerfile
├── requirements.txt
├── app.py                 # 主应用入口
├── database.py            # MongoDB连接
├── config.py              # 配置文件
├── .env.example           # 环境变量示例
├── models/
│   ├── user.py           # User模型
│   ├── conversation.py   # Conversation模型
│   └── diary.py          # Diary模型
├── routes/
│   ├── user_routes.py    # 用户相关路由
│   ├── conversation_routes.py  # 对话路由
│   └── diary_routes.py   # 日记路由
├── utils/
│   └── ai_client.py      # AI Service客户端
└── tests/
    ├── test_users.py
    ├── test_conversations.py
    └── test_diaries.py
```

#### 核心功能
1. **用户管理**
   - 创建用户
   - 获取用户信息

2. **对话管理**
   - 创建新对话
   - 添加消息（接收音频→调用AI Service转录→获取AI回复）
   - 完成对话

3. **日记管理**
   - 生成日记（调用AI Service）
   - 获取用户所有日记
   - 获取单篇日记详情

4. **前端页面**
   - 首页（开始对话）
   - 对话界面
   - 日记列表
   - 日记详情

### 4.2 AI Service 模块

#### 文件结构
```
ai-service/
├── Dockerfile
├── requirements.txt
├── service.py            # 主服务入口
├── .env.example
├── modules/
│   ├── transcription.py  # Whisper转录
│   ├── chat.py          # Gemini对话
│   └── diary_gen.py     # Gemini日记生成
├── utils/
│   └── helpers.py       # 辅助函数
└── tests/
    ├── test_transcription.py
    ├── test_chat.py
    └── test_diary.py
```

#### 核心功能
1. **语音转文字**
   - 接收音频文件
   - 使用Whisper Base模型转录
   - 返回文字结果

2. **AI对话**
   - 接收对话历史
   - 使用Gemini Pro生成回复
   - 返回AI回复

3. **生成日记**
   - 接收完整对话
   - 使用Gemini Pro生成日记
   - 返回标题和正文

---

## 5. API接口规范

### 5.1 Flask App 对外API

#### 用户相关

**创建用户**
```
POST /api/users
Content-Type: application/json

Request:
{
  "username": "john_doe",
  "email": "john@example.com"
}

Response:
{
  "user_id": "507f1f77bcf86cd799439011",
  "username": "john_doe"
}
```

#### 对话相关

**开始新对话**
```
POST /api/conversations
Content-Type: application/json

Request:
{
  "user_id": "507f1f77bcf86cd799439011"
}

Response:
{
  "conversation_id": "507f...",
  "first_message": "Hi! How was your day?"
}
```

**发送消息**
```
POST /api/conversations/{conversation_id}/messages
Content-Type: multipart/form-data

Request:
- audio: <audio_file> (webm/mp3格式)

Response:
{
  "user_message": "It was great! I had a meeting.",
  "ai_response": "That's wonderful! Tell me more..."
}
```

**完成对话并生成日记**
```
POST /api/conversations/{conversation_id}/complete

Response:
{
  "diary_id": "507f...",
  "title": "A Productive Monday",
  "content": "Today was an amazing day..."
}
```

#### 日记相关

**获取用户所有日记**
```
GET /api/users/{user_id}/diaries?page=1&limit=10

Response:
{
  "diaries": [
    {
      "diary_id": "507f...",
      "date": "2024-01-15",
      "title": "A Productive Monday",
      "preview": "Today was amazing..."
    }
  ],
  "total": 45,
  "page": 1,
  "pages": 5
}
```

**获取单篇日记**
```
GET /api/diaries/{diary_id}

Response:
{
  "diary_id": "507f...",
  "date": "2024-01-15",
  "title": "A Productive Monday",
  "content": "完整日记内容..."
}
```

### 5.2 AI Service 内部API

#### 语音转文字
```
POST /transcribe
Content-Type: multipart/form-data

Request:
- audio: <audio_file>

Response:
{
  "text": "It was great! I had a productive meeting."
}
```

#### AI对话
```
POST /chat
Content-Type: application/json

Request:
{
  "messages": [
    {"role": "assistant", "content": "Hi! How was your day?"},
    {"role": "user", "content": "It was great!"}
  ]
}

Response:
{
  "response": "That's wonderful! What made it great?"
}
```

#### 生成日记
```
POST /generate-diary
Content-Type: application/json

Request:
{
  "messages": [
    {"role": "assistant", "content": "Hi! How was your day?"},
    {"role": "user", "content": "It was great! I had a meeting."},
    ...
  ]
}

Response:
{
  "title": "A Productive Monday",
  "content": "Today was an amazing day. I had a very productive meeting..."
}
```

---

## 6. 部署方案

### 6.1 Docker Compose（本地开发）

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:7.0
    container_name: ai-diary-mongodb
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
    networks:
      - diary-network

  ai-service:
    build: ./ai-service
    container_name: ai-diary-ai-service
    ports:
      - "5001:5001"
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
    networks:
      - diary-network
    restart: unless-stopped

  flask-app:
    build: ./flask-app
    container_name: ai-diary-flask-app
    ports:
      - "5000:5000"
    environment:
      - MONGO_URI=mongodb://mongodb:27017/diary_db
      - AI_SERVICE_URL=http://ai-service:5001
    depends_on:
      - mongodb
      - ai-service
    networks:
      - diary-network
    restart: unless-stopped

volumes:
  mongo_data:

networks:
  diary-network:
    driver: bridge
```

### 6.2 Digital Ocean部署

#### 准备工作
1. 创建Digital Ocean账号
2. 创建Droplet（Ubuntu 22.04，Basic Plan $6/月）
3. 安装Docker和Docker Compose
4. 设置域名（可选）

#### 部署步骤
```bash
# 1. SSH登录Droplet
ssh root@your_droplet_ip

# 2. 安装Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 3. 安装Docker Compose
apt install docker-compose-plugin

# 4. 克隆项目
git clone https://github.com/your-team/ai-diary-project.git
cd ai-diary-project

# 5. 配置环境变量
cp .env.example .env
nano .env  # 填入API密钥

# 6. 启动服务
docker compose up -d

# 7. 查看日志
docker compose logs -f
```

### 6.3 CI/CD流程

#### GitHub Actions工作流

**Flask App CI/CD** (`.github/workflows/flask-app.yml`)
```yaml
name: Flask App CI/CD

on:
  push:
    branches: [main, master]
    paths:
      - 'flask-app/**'
  pull_request:
    branches: [main, master]
    paths:
      - 'flask-app/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: |
          cd flask-app
          pip install -r requirements.txt
          pip install pytest pytest-cov
      
      - name: Run tests with coverage
        run: |
          cd flask-app
          pytest --cov=. --cov-report=xml --cov-report=term
      
      - name: Check coverage
        run: |
          cd flask-app
          coverage report --fail-under=80

  build-and-deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Login to Docker Hub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      
      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: ./flask-app
          push: true
          tags: yourteam/ai-diary-flask-app:latest
      
      - name: Deploy to Digital Ocean
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.DO_HOST }}
          username: ${{ secrets.DO_USERNAME }}
          key: ${{ secrets.DO_SSH_KEY }}
          script: |
            cd /root/ai-diary-project
            docker compose pull flask-app
            docker compose up -d flask-app
```

**AI Service CI/CD** (`.github/workflows/ai-service.yml`)
```yaml
name: AI Service CI/CD

on:
  push:
    branches: [main, master]
    paths:
      - 'ai-service/**'
  pull_request:
    branches: [main, master]
    paths:
      - 'ai-service/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: |
          cd ai-service
          pip install -r requirements.txt
          pip install pytest pytest-cov
      
      - name: Run tests with coverage
        run: |
          cd ai-service
          pytest --cov=. --cov-report=xml --cov-report=term
      
      - name: Check coverage
        run: |
          cd ai-service
          coverage report --fail-under=80

  build-and-deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Login to Docker Hub
        uses: docker/login-action@v2
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      
      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: ./ai-service
          push: true
          tags: yourteam/ai-diary-ai-service:latest
      
      - name: Deploy to Digital Ocean
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.DO_HOST }}
          username: ${{ secrets.DO_USERNAME }}
          key: ${{ secrets.DO_SSH_KEY }}
          script: |
            cd /root/ai-diary-project
            docker compose pull ai-service
            docker compose up -d ai-service
```

---

## 7. 五人分工方案

### 👤 Person 1: 项目负责人 + Flask后端核心

**职责：**
- 项目整体协调
- Flask App主框架搭建
- MongoDB连接和数据模型设计
- 用户和对话相关API

**任务清单：**
- [ ] 初始化项目结构
- [ ] 设计数据库Schema
- [ ] 实现User CRUD
- [ ] 实现Conversation API
- [ ] 编写Flask App单元测试
- [ ] 集成其他模块

**交付物：**
- `flask-app/app.py`
- `flask-app/database.py`
- `flask-app/models/`
- `flask-app/routes/user_routes.py`
- `flask-app/routes/conversation_routes.py`

---

### 👤 Person 2: AI Service核心开发

**职责：**
- AI Service完整实现
- Whisper语音转文字
- Gemini对话和日记生成
- AI Service单元测试

**任务清单：**
- [ ] 搭建AI Service Flask框架
- [ ] 集成Whisper模型
- [ ] 集成Google Gemini API
- [ ] 实现三个API接口
- [ ] 编写AI Service单元测试
- [ ] 性能优化

**交付物：**
- `ai-service/service.py`
- `ai-service/modules/transcription.py`
- `ai-service/modules/chat.py`
- `ai-service/modules/diary_gen.py`
- `ai-service/tests/`

---

### 👤 Person 3: 前端 + 日记模块

**职责：**
- 前端界面开发
- 麦克风录音功能
- 日记相关API
- 前端与后端联调

**任务清单：**
- [ ] 设计并实现录音界面
- [ ] 实现麦克风录音功能
- [ ] 实现对话界面（实时显示对话）
- [ ] 实现日记列表和详情页面
- [ ] Flask App中的日记路由
- [ ] 前后端联调测试

**交付物：**
- `flask-app/templates/` (HTML模板)
- `flask-app/static/` (CSS/JS)
- `flask-app/routes/diary_routes.py`
- 用户界面完整Demo

---

### 👤 Person 4: DevOps + Docker + CI/CD

**职责：**
- Docker容器化
- CI/CD流程搭建
- Digital Ocean部署
- 监控和日志

**任务清单：**
- [ ] 编写所有Dockerfile
- [ ] 编写docker-compose.yml
- [ ] 配置GitHub Actions工作流
- [ ] 设置Docker Hub自动构建
- [ ] Digital Ocean Droplet配置
- [ ] 部署和监控
- [ ] 编写部署文档

**交付物：**
- `flask-app/Dockerfile`
- `ai-service/Dockerfile`
- `docker-compose.yml`
- `.github/workflows/`
- 部署文档
- 运行中的生产环境

---

### 👤 Person 5: 测试 + 文档 + 集成

**职责：**
- 单元测试覆盖率监控
- 集成测试
- 完善项目文档
- Bug修复和优化

**任务清单：**
- [ ] 确保所有模块单元测试覆盖率≥80%
- [ ] 编写端到端集成测试
- [ ] 编写详细的README.md
- [ ] 创建API文档
- [ ] 编写.env.example
- [ ] 用户使用手册
- [ ] 协助其他成员调试

**交付物：**
- `README.md` (完整项目文档)
- `API_DOCUMENTATION.md`
- `SETUP_GUIDE.md`
- `.env.example`
- 集成测试脚本
- CI/CD状态徽章

---

## 8. 开发时间线

### Week 1: 基础搭建（Day 1-7）

**Day 1-2: 项目初始化**
- Person 1: 创建GitHub repo，初始化Flask项目结构
- Person 2: 初始化AI Service项目结构
- Person 4: 准备本地开发环境（Docker）
- Person 5: 创建项目文档模板

**Day 3-4: 核心功能开发**
- Person 1: 完成MongoDB连接和User模型
- Person 2: 集成Whisper和Gemini，完成基础API
- Person 3: 开发基础前端界面（HTML/CSS）
- Person 4: 编写Dockerfile

**Day 5-7: 功能集成**
- Person 1: 完成Conversation API
- Person 2: 优化AI响应速度
- Person 3: 实现录音功能
- Person 4: 编写docker-compose.yml
- Person 5: 开始编写单元测试

### Week 2: 功能完善（Day 8-14）

**Day 8-10: 主要功能**
- Person 1: 实现完整对话流程
- Person 2: 完成日记生成功能
- Person 3: 实现日记显示页面
- Person 4: 配置CI/CD工作流
- Person 5: 确保测试覆盖率

**Day 11-12: 集成测试**
- 全员: 本地环境完整测试
- Person 3: 前后端联调
- Person 5: 端到端测试

**Day 13-14: 部署和文档**
- Person 4: 部署到Digital Ocean
- Person 5: 完善所有文档
- 全员: 修复部署中的问题

### Week 3: 优化和演示（Day 15-21）

**Day 15-17: Bug修复**
- 全员: 修复已知问题
- Person 1 & 2: 性能优化
- Person 3: UI优化

**Day 18-19: 最终测试**
- Person 5: 完整测试所有功能
- 全员: 交叉测试

**Day 20-21: 准备演示**
- 准备演示视频
- 准备演示PPT
- 最终文档审查

---

## 9. 技术选型说明

### 9.1 为什么选择这些技术？

**Flask vs Django vs FastAPI**
- ✅ Flask: 轻量、灵活、适合小项目
- ❌ Django: 太重，功能过多
- ❌ FastAPI: 异步特性对MVP不必要

**Whisper vs Google Speech-to-Text**
- ✅ Whisper: 完全免费，本地运行
- ❌ Google STT: 需要API配额限制

**Gemini vs GPT-3.5 vs Claude**
- ✅ Gemini: 完全免费，配额大
- ⚠️ GPT-3.5: $5免费额度，质量稍好
- ❌ Claude: 需要付费

**MongoDB vs PostgreSQL**
- ✅ MongoDB: 文档型存储，适合灵活Schema
- ❌ PostgreSQL: 关系型，对对话历史不够灵活

### 9.2 免费资源汇总

| 服务 | 免费额度 | 备注 |
|------|---------|------|
| Google Gemini API | 60次/分钟 | 完全免费 |
| Whisper | 无限制 | 本地运行 |
| Docker Hub | 无限公开仓库 | 需注册 |
| GitHub Actions | 2000分钟/月 | 公开repo |
| Digital Ocean | $200试用额度 | 新用户 |
| MongoDB | 无限制 | 使用官方Docker镜像 |

### 9.3 开发工具推荐

**必备工具：**
- Git
- Docker Desktop
- VSCode / PyCharm
- Postman（API测试）

**VSCode插件：**
- Python
- Docker
- GitLens
- REST Client

---

## 10. 注意事项

### 10.1 常见问题

**Q1: 音频格式兼容性？**
- 浏览器录音通常是webm格式
- Whisper支持mp3/wav/webm/m4a等
- 如果有问题，可以用ffmpeg转换

**Q2: MongoDB连接问题？**
- 确保在docker-compose中设置正确的网络
- 使用服务名而不是localhost（如`mongodb://mongodb:27017`）

**Q3: Whisper模型下载慢？**
- 在Dockerfile中预下载模型
- 使用国内镜像源（如果需要）

**Q4: CI/CD失败？**
- 检查GitHub Secrets是否配置正确
- 确保Docker Hub凭证有效
- 检查Digital Ocean SSH密钥

**Q5: 测试覆盖率不足80%？**
- 重点测试业务逻辑
- 可以跳过简单的getter/setter
- 使用mock减少外部依赖

### 10.2 安全提醒

**不要提交到Git的文件：**
- `.env` (包含API密钥)
- `__pycache__/`
- `*.pyc`
- `.pytest_cache/`
- Docker数据卷

**必须创建.gitignore：**
```
.env
__pycache__/
*.pyc
.pytest_cache/
*.db
venv/
.DS_Store
```

### 10.3 代码规范

**Python代码风格：**
- 遵循PEP 8
- 函数和变量使用snake_case
- 类名使用PascalCase
- 添加docstring注释

**Git提交规范：**
```
feat: 添加新功能
fix: 修复bug
docs: 更新文档
test: 添加测试
refactor: 重构代码
style: 代码格式调整
```

### 10.4 项目检查清单

**提交前确认：**
- [ ] 所有测试通过
- [ ] 代码覆盖率 ≥ 80%
- [ ] README.md完整
- [ ] 所有Dockerfile可以构建
- [ ] docker-compose.yml可以运行
- [ ] .env.example包含所有必需变量
- [ ] CI/CD workflows正常工作
- [ ] 生产环境可访问
- [ ] API文档完整
- [ ] 所有徽章显示passing

---

## 附录A: 环境变量配置

### `.env.example`

```bash
# Google Gemini API
GOOGLE_API_KEY=your_api_key_here

# MongoDB Configuration
MONGO_URI=mongodb://mongodb:27017/diary_db

# AI Service URL
AI_SERVICE_URL=http://ai-service:5