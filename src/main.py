"""Modbus to MQTT Bridge 主程序"""
import os
import sys
import json
import time
import logging
import signal
import threading
from pathlib import Path
from typing import List, Dict
from src.config_parser import ConfigParser, ModbusDevice
from src.modbus_poller import ModbusPoller
from src.mqtt_publisher import MQTTPublisher

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class DevicePoller(threading.Thread):
    """设备轮询线程"""
    
    def __init__(self, device: ModbusDevice, poller: ModbusPoller, 
                 publisher: MQTTPublisher, base_topic: str):
        super().__init__(daemon=True)
        self.device = device
        self.poller = poller
        self.publisher = publisher
        self.base_topic = base_topic
        self.running = False
        self.name = f"Poller-{device.name}"
    
    def run(self):
        """运行轮询循环"""
        logger.info(f"Started polling thread for '{self.device.name}' "
                   f"(interval: {self.device.poll_interval}s)")
        self.running = True
        
        while self.running:
            try:
                # 轮询设备
                device_data = self.poller.poll_device(self.device)
                
                # 发布数据
                if device_data['data']:
                    self.publisher.publish(device_data, self.base_topic)
                else:
                    logger.warning(f"No data from '{self.device.name}'")
                
                # 等待下一次轮询
                time.sleep(self.device.poll_interval)
            
            except Exception as e:
                logger.error(f"Error in polling thread for '{self.device.name}': {e}", 
                           exc_info=True)
                time.sleep(5)  # 错误后等待5秒
    
    def stop(self):
        """停止轮询"""
        logger.info(f"Stopping polling thread for '{self.device.name}'")
        self.running = False


class ModbusMQTTBridge:
    """Modbus to MQTT 桥接服务"""
    
    def __init__(self, config_dir: str, mqtt_config: dict):
        """初始化桥接服务"""
        self.config_dir = Path(config_dir)
        self.devices: List[ModbusDevice] = []
        self.poller = ModbusPoller()
        self.publisher: MQTTPublisher = None
        self.polling_threads: List[DevicePoller] = []
        self.running = False
        self.mqtt_config = mqtt_config
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def load_configs(self):
        """加载所有配置文件"""
        logger.info(f"Loading configs from {self.config_dir}")
        
        config_files = sorted(self.config_dir.glob("usb*_config.json"))
        
        if not config_files:
            logger.error(f"No config files found in {self.config_dir}")
            return
        
        for config_file in config_files:
            try:
                devices = ConfigParser.parse_thingsboard_config(str(config_file))
                self.devices.extend(devices)
            except Exception as e:
                logger.error(f"Failed to parse {config_file.name}: {e}", exc_info=True)
        
        logger.info(f"✓ Loaded {len(self.devices)} devices from {len(config_files)} config files")
        
        for device in self.devices:
            logger.info(f"  - {device.name} ({device.device_type}) "
                       f"on {device.port}, {len(device.registers)} registers")
    
    def connect_mqtt(self):
        """连接 MQTT broker"""
        logger.info("Connecting to MQTT broker...")
        
        self.publisher = MQTTPublisher(
            broker=self.mqtt_config.get('broker', 'localhost'),
            port=self.mqtt_config.get('port', 1883),
            username=self.mqtt_config.get('username'),
            password=self.mqtt_config.get('password'),
            client_id=self.mqtt_config.get('client_id', 'modbus-mqtt-bridge')
        )
        
        self.publisher.connect(retry=5)
    
    def start_polling(self):
        """启动设备轮询线程"""
        base_topic = self.mqtt_config.get('base_topic', 'modbus')
        
        logger.info(f"Starting polling threads for {len(self.devices)} devices")
        
        for i, device in enumerate(self.devices):
            thread = DevicePoller(device, self.poller, self.publisher, base_topic)
            thread.start()
            self.polling_threads.append(thread)
            
            # 为每个线程添加启动延迟，避免同时访问串口
            if i < len(self.devices) - 1:  # 最后一个不需要延迟
                time.sleep(0.2)  # 200ms 启动间隔
        
        logger.info(f"✓ Started {len(self.polling_threads)} polling threads")
    
    def run(self):
        """运行主服务"""
        logger.info("=" * 60)
        logger.info("Modbus to MQTT Bridge v1.0.0")
        logger.info("=" * 60)
        
        # 1. 加载配置
        self.load_configs()
        if not self.devices:
            logger.error("No devices configured, exiting")
            return 1
        
        # 2. 连接 MQTT
        try:
            self.connect_mqtt()
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            return 1
        
        # 3. 启动轮询
        self.start_polling()
        
        # 4. 主循环（保持运行）
        self.running = True
        logger.info("=" * 60)
        logger.info("✓ Bridge is running. Press Ctrl+C to stop.")
        logger.info("=" * 60)
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()
        
        return 0
    
    def stop(self):
        """停止服务"""
        if not self.running:
            return
        
        logger.info("Stopping Modbus to MQTT Bridge...")
        self.running = False
        
        # 停止轮询线程
        for thread in self.polling_threads:
            thread.stop()
        
        # 等待线程结束
        for thread in self.polling_threads:
            thread.join(timeout=5)
        
        # 关闭 Modbus 连接
        self.poller.close_all()
        
        # 断开 MQTT
        if self.publisher:
            self.publisher.disconnect()
        
        logger.info("✓ Bridge stopped")


def main():
    """主函数"""
    # 读取环境变量
    config_dir = os.getenv('CONFIG_DIR', '/app/config')
    mqtt_config_path = os.getenv('MQTT_CONFIG', '/app/config/mqtt_config.json')
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    # 设置日志级别
    logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # 加载 MQTT 配置
    if Path(mqtt_config_path).exists():
        try:
            with open(mqtt_config_path, 'r') as f:
                mqtt_config = json.load(f)
            logger.info(f"Loaded MQTT config from {mqtt_config_path}")
        except Exception as e:
            logger.error(f"Failed to load MQTT config: {e}")
            mqtt_config = {}
    else:
        logger.warning(f"MQTT config not found at {mqtt_config_path}, using environment variables")
        mqtt_config = {}
    
    # 环境变量覆盖
    mqtt_config.setdefault('broker', os.getenv('MQTT_BROKER', 'mosquitto'))
    mqtt_config.setdefault('port', int(os.getenv('MQTT_PORT', '1883')))
    mqtt_config.setdefault('username', os.getenv('MQTT_USERNAME'))
    mqtt_config.setdefault('password', os.getenv('MQTT_PASSWORD'))
    mqtt_config.setdefault('base_topic', os.getenv('MQTT_BASE_TOPIC', 'modbus'))
    mqtt_config.setdefault('client_id', os.getenv('MQTT_CLIENT_ID', 'modbus-mqtt-bridge'))
    
    # 启动桥接服务
    bridge = ModbusMQTTBridge(config_dir, mqtt_config)
    sys.exit(bridge.run())


if __name__ == '__main__':
    main()