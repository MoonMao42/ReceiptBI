# QueryGPT API 文档

## 概述

QueryGPT API 提供了完整的RESTful接口，用于自然语言数据查询、可视化生成和历史管理。

## 文档内容

### 📄 [OpenAPI 规范](./openapi.yaml)
完整的OpenAPI 3.0规范文档，定义了所有API端点、请求/响应模式、参数说明等。

### 💻 [使用示例](./examples.md)
多种编程语言的API调用示例：
- Python
- JavaScript/Node.js
- cURL
- Java
- Go
- C#/.NET

## 快速开始

### 1. 启动服务
```bash
cd /Users/your-name/QueryGPT-github
python backend/app.py
```

### 2. 访问交互式文档
启动服务后，访问以下地址查看交互式API文档：
```
http://localhost:5001/api/docs/
```

### 3. 基本使用流程

#### 步骤1: 检查服务健康状态
```bash
curl http://localhost:5001/api/health
```

#### 步骤2: 获取系统配置
```bash
curl http://localhost:5001/api/config
```

#### 步骤3: 测试数据库连接
```bash
curl -X POST http://localhost:5001/api/database/test \
  -H "Content-Type: application/json" \
  -d '{
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "your_password",
    "database": "your_database"
  }'
```

#### 步骤4: 执行查询
```bash
curl -X POST http://localhost:5001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "查询销售数据"}'
```

## API端点概览

### 核心功能
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/chat` | POST | 执行自然语言查询 |
| `/api/execute_sql` | POST | 执行SQL查询（只读） |
| `/api/stop_query` | POST | 停止正在执行的查询 |

### 配置管理
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/config` | GET/POST | 获取/更新系统配置 |
| `/api/models` | GET/POST | 获取/保存模型列表 |
| `/api/test_model` | POST | 测试模型连接 |

### 数据库管理
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/schema` | GET | 获取数据库结构 |
| `/api/test_connection` | GET | 测试数据库连接 |
| `/api/database/test` | POST | 测试数据库连接（带参数） |
| `/api/database/config` | POST | 保存数据库配置 |

### 历史管理
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/history/conversations` | GET | 获取对话历史列表 |
| `/api/history/conversation/{id}` | GET | 获取对话详情 |
| `/api/history/conversation/{id}` | DELETE | 删除对话 |
| `/api/history/conversation/{id}/favorite` | POST | 切换收藏状态 |
| `/api/history/statistics` | GET | 获取统计信息 |
| `/api/history/cleanup` | POST | 清理历史记录 |
| `/api/history/replay/{id}` | POST | 复现对话 |

### 系统状态
| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/` | GET | Web界面 |

## 认证机制

### 可选认证
API支持可选的Bearer Token认证。如果配置了`API_ACCESS_SECRET`环境变量，则需要认证。

### 设置认证
1. 在`.env`文件中设置：
```bash
API_ACCESS_SECRET=your_secret_key
```

2. 在请求头中包含Token：
```
Authorization: Bearer <your-token>
```

### 获取Token
Token生成需要通过服务端API（需要根据实际需求实现）。

## 速率限制

| 端点 | 限制 |
|------|------|
| `/api/chat` | 30次/分钟 |
| 其他端点 | 无限制 |

## 响应格式

### 成功响应
```json
{
  "success": true,
  "data": { ... },
  "message": "操作成功"
}
```

### 错误响应
```json
{
  "success": false,
  "error": "错误描述"
}
```

## 支持的模型

- `gpt-4.1` - GPT-4.1
- `claude-sonnet-4` - Claude Sonnet 4
- `deepseek-r1` - DeepSeek R1
- `qwen-flagship` - Qwen 旗舰模型

## 数据库支持

- MySQL 5.7+
- MariaDB 10.3+
- 支持中文表名和字段名
- UTF-8编码

## 集成Swagger UI

要在Flask应用中启用Swagger UI，需要：

1. 安装依赖：
```bash
pip install flasgger pyyaml
```

2. 在`app.py`中添加：
```python
from backend.swagger import init_swagger

# 在app初始化后添加
swagger = init_swagger(app)
```

3. 访问交互式文档：
```
http://localhost:5001/api/docs/
```

## 开发工具

### Postman Collection
可以将`openapi.yaml`导入Postman生成测试集合。

### VS Code插件
推荐安装以下插件：
- REST Client
- Thunder Client
- OpenAPI (Swagger) Editor

### 在线工具
- [Swagger Editor](https://editor.swagger.io/)
- [OpenAPI Generator](https://openapi-generator.tech/)

## 故障排除

### 常见问题

1. **连接被拒绝**
   - 检查服务是否启动
   - 确认端口5001未被占用

2. **认证失败**
   - 检查Token是否正确
   - 确认`API_ACCESS_SECRET`配置

3. **数据库连接失败**
   - 使用`127.0.0.1`代替`localhost`
   - 检查数据库服务状态
   - 验证用户名密码

4. **速率限制**
   - 实现客户端速率限制
   - 使用指数退避重试

## 更新日志

### v0.4.3
- 添加OpenAPI 3.0规范
- 支持Swagger UI
- 新增多语言示例代码
- 改进错误处理

## 支持

如有问题，请：
1. 查看[使用示例](./examples.md)
2. 检查[OpenAPI规范](./openapi.yaml)
3. 提交Issue到项目仓库