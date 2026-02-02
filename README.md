# Modbus to MQTT Bridge

🚀 基于 pymodbus 的轻量化 Modbus RTU 数据采集与 MQTT 发布服务

## ✨ 特性

- ✅ **完全兼容** ThingsBoard Gateway Modbus Connector 配置格式
- ✅ **轻量化设计** 基于 Alpine Linux，镜像 < 100MB
- ✅ **多设备支持** 自动解析多个配置文件
- ✅ **独立轮询** 每个设备独立线程，互不干扰
- ✅ **实时发布** JSON 格式通过 MQTT 实时推送
- ✅ **容器化部署** Docker Compose 一键启动
- ✅ **生产就绪** 健康检查、日志管理、优雅退出

## 📊 架构

```
┌─────────────────┐
│  Modbus 设备    │
│  - 数字IO       │
│  - 空气质量     │
│  - 电表/水表    │
└────────┬────────┘
         │ RTU
         │ /dev/ttyTB0, /dev/ttyTB1
         ↓
┌─────────────────┐
│  Modbus Bridge  │
│  - pymodbus     │
│  - 多线程轮询    │
└────────┬────────┘
         │ MQTT
         ↓
┌─────────────────┐
│  Mosquitto      │
│  - 局域网可访问  │
└────────┬────────┘
         │
         ↓
    订阅者 (MQTT Client)
```

## 📁 项目结构

```
modbus-mqtt-bridge/
├── docker compose.yml      # Docker Compose 配置
├── Dockerfile             # 容器构建文件
├── requirements.txt       # Python 依赖
├── README.md             
├── config/               # 配置目录
│   ├── usb00_config.json # USB0 设备配置
│   ├── usb01_config.json # USB1 设备配置
│   └── mqtt_config.json  # MQTT 配置
├── mosquitto/
│   └── config/
│       └── mosquitto.conf # MQTT Broker 配置
└── src/                  # 源代码
    ├── __init__.py
    ├── main.py          # 主程序
    ├── config_parser.py # 配置解析
    ├── modbus_poller.py # Modbus 轮询
    └── mqtt_publisher.py # MQTT 发布
```

## 🔧 配置说明

### MQTT Topic 结构

```
modbus/
├── {device_name}/
│   ├── status              # 设备状态
│   ├── telemetry           # 完整遥测数据
│   ├── {tag1}              # 单个数据点
│   ├── {tag2}
│   └── ...
```

#### 示例 Topic 和 Payload

**状态消息**
```
Topic: modbus/数字量输入输出设备/status
Payload:
{
  "status": "connected",
  "timestamp": "2026-02-02T10:30:00.123456Z"
}
```

**遥测数据**
```
Topic: modbus/空气质量传感器/telemetry
Payload:
{
  "device": "空气质量传感器",
  "device_type": "空气质量传感器",
  "unit_id": 3,
  "timestamp": "2026-02-02T10:30:00.123456Z",
  "data": {
    "temp": 23.5,
    "humid": 65.3,
    "pm_2.5": 35,
    "NH3": 120
  }
}
```

**单个数据点**
```
Topic: modbus/单相电表/voltage
Payload:
{
  "value": 220.5,
  "timestamp": "2026-02-02T10:30:00.123456Z"
}
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CONFIG_DIR` | `/app/config` | 配置文件目录 |
| `MQTT_BROKER` | `mosquitto` | MQTT Broker 地址 |
| `MQTT_PORT` | `1883` | MQTT 端口 |
| `MQTT_USERNAME` | `null` | MQTT 用户名 |
| `MQTT_PASSWORD` | `null` | MQTT 密码 |
| `MQTT_BASE_TOPIC` | `modbus` | MQTT 基础主题 |
| `LOG_LEVEL` | `INFO` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |

## 🚀 快速开始

### 1. 准备配置文件

```bash
# 创建目录结构
mkdir -p config mosquitto/config

# 复制你的 ThingsBoard 配置
cp usb00_config.json config/
cp usb01_config.json config/

# 创建 MQTT 配置（可选，也可使用环境变量）
cat > config/mqtt_config.json <<EOF
{
  "broker": "mosquitto",
  "port": 1883,
  "username": null,
  "password": null,
  "client_id": "modbus-mqtt-bridge",
  "base_topic": "modbus"
}
EOF
```

### 2. 启动服务

```bash
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f modbus-mqtt-bridge

# 查看所有服务状态
docker compose ps
```

### 3. 测试 MQTT 消息

```bash
# 订阅所有 Modbus 数据
mosquitto_sub -h localhost -t "modbus/#" -v

# 订阅特定设备
mosquitto_sub -h localhost -t "modbus/空气质量传感器/#" -v

# 订阅特定数据点
mosquitto_sub -h localhost -t "modbus/单相电表/voltage" -v

# 订阅所有遥测数据
mosquitto_sub -h localhost -t "modbus/+/telemetry" -v
```

## 📊 监控和日志

### 查看实时日志

```bash
# 查看桥接服务日志
docker compose logs -f modbus-mqtt-bridge

# 查看 MQTT broker 日志
docker compose logs -f mosquitto

# 查看最近 100 行
docker compose logs --tail=100 modbus-mqtt-bridge
```

### 健康检查

```bash
# 检查服务健康状态
docker compose ps

# 进入容器检查
docker compose exec modbus-mqtt-bridge ps aux
```

## 🔍 故障排查

### 1. 串口权限问题

```bash
# 检查串口设备
ls -l /dev/ttyTB*

# 添加当前用户到 dialout 组
sudo usermod -a -G dialout $USER

# 或者修改设备权限
sudo chmod 666 /dev/ttyTB0 /dev/ttyTB1
```

### 2. 连接失败

```bash
# 检查设备配置
docker compose exec modbus-mqtt-bridge cat /app/config/usb00_config.json

# 测试 Modbus 连接（进入容器）
docker compose exec modbus-mqtt-bridge python3 -c "
from pymodbus.client import ModbusSerialClient
client = ModbusSerialClient(port='/dev/ttyTB0', baudrate=9600, parity='N')
print('Connected:', client.connect())
client.close()
"
```

### 3. MQTT 发布失败

```bash
# 检查 MQTT broker 状态
docker compose exec mosquitto mosquitto_sub -t '$SYS/#' -v -C 10

# 测试发布
docker compose exec mosquitto mosquitto_pub -t "test" -m "hello"

# 测试订阅
docker compose exec mosquitto mosquitto_sub -t "test" -v
```

### 4. 查看详细调试日志

```bash
# 修改 docker compose.yml 中的日志级别
environment:
  - LOG_LEVEL=DEBUG

# 重启服务
docker compose restart modbus-mqtt-bridge
```

## ⚙️ 高级配置

### 自定义轮询间隔

在 ThingsBoard 配置文件中，每个设备有独立的 `pollPeriod`（毫秒）：

```json
{
  "pollPeriod": 5000,  // 5秒轮询一次
  ...
}
```

### MQTT 认证

```yaml
# docker compose.yml
environment:
  - MQTT_USERNAME=your_username
  - MQTT_PASSWORD=your_password
```

```conf
# mosquitto/config/mosquitto.conf
allow_anonymous false
password_file /mosquitto/config/passwd

# 创建密码文件
docker compose exec mosquitto mosquitto_passwd -c /mosquitto/config/passwd username
```

### 数据缩放和转换

配置文件支持 `divider` 和 `multiplier`：

```json
{
  "tag": "voltage",
  "address": 400,
  "functionCode": 4,
  "divider": 10,        // 原始值 / 10
  "multiplier": 1.0     // 可选
}
```

## 📈 性能指标

- **镜像大小**: ~80-100 MB
- **内存占用**: ~30-50 MB（运行时）
- **CPU 使用**: < 5%（轮询时）
- **启动时间**: < 5 秒
- **支持设备**: 理论无限（受串口数量限制）

## 🛠️ 开发和调试

### 本地开发

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 运行
export CONFIG_DIR=./config
export MQTT_BROKER=localhost
python -m src.main
```

### 单元测试

```bash
# 测试配置解析
python3 -c "
from src.config_parser import ConfigParser
devices = ConfigParser.parse_thingsboard_config('config/usb00_config.json')
print(f'Loaded {len(devices)} devices')
for d in devices:
    print(f'  - {d.name}: {len(d.registers)} registers')
"
```

## 📝 更新日志


### v1.0.1 (2026-02-02)
- 🛠️ 修复 Mosquitto 镜像版本兼容性
- 🛠️ docker-compose 命令统一为新版语法
- 🛠️ requirements.txt 依赖规范化（paho-mqtt/pyserial）
- 🛠️ 串口设备访问权限优化（group_add 配置）
- 🛠️ Modbus 设备超时与轮询机制优化
- 🛠️ 增加串口访问线程锁，提升多设备稳定性
- 🛠️ 轮询启动错开，提升数据完整性
- 🛠️ 清理无用设备配置

### v1.0.0 (2026-02-02)
- ✅ 初始版本
- ✅ 支持 ThingsBoard Gateway 配置格式
- ✅ 基于 pymodbus 实现
- ✅ 多线程独立轮询
- ✅ Docker Compose 部署

## 📄 License

[GPL v3 License](./LICENSE)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**Made with ❤️ by Ellean**
