"""MQTT 数据发布器"""
import json
import logging
from typing import Dict, Any
from datetime import datetime
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTPublisher:
    """MQTT 数据发布器"""
    
    def __init__(self, broker: str, port: int = 1883, 
                 username: str = None, password: str = None,
                 client_id: str = "modbus-mqtt-bridge"):
        """初始化 MQTT 客户端"""
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        
        if username and password:
            self.client.username_pw_set(username, password)
        
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self.connected = False
        self.message_count = 0
    
    def _on_connect(self, client, userdata, flags, rc):
        """连接回调"""
        if rc == 0:
            logger.info(f"✓ Connected to MQTT broker {self.broker}:{self.port}")
            self.connected = True
        else:
            logger.error(f"✗ Failed to connect to MQTT broker, code: {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调"""
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker, code: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")
        self.connected = False
    
    def _on_publish(self, client, userdata, mid):
        """发布回调"""
        self.message_count += 1
    
    def connect(self, retry: int = 5):
        """连接到 MQTT broker"""
        for attempt in range(retry):
            try:
                logger.info(f"Connecting to MQTT broker {self.broker}:{self.port} (attempt {attempt + 1}/{retry})")
                self.client.connect(self.broker, self.port, 60)
                self.client.loop_start()
                
                # 等待连接建立
                import time
                timeout = 5
                start = time.time()
                while not self.connected and (time.time() - start) < timeout:
                    time.sleep(0.1)
                
                if self.connected:
                    return True
                
            except Exception as e:
                logger.error(f"Failed to connect to MQTT broker: {e}")
                if attempt < retry - 1:
                    import time
                    time.sleep(2)
        
        raise ConnectionError(f"Failed to connect to MQTT broker after {retry} attempts")
    
    def disconnect(self):
        """断开连接"""
        logger.info(f"Total messages published: {self.message_count}")
        self.client.loop_stop()
        self.client.disconnect()
    
    def publish(self, device_data: Dict[str, Any], base_topic: str = "modbus"):
        """发布设备数据
        
        Topic 结构:
        - modbus/{device_name}/telemetry - 完整遥测数据
        - modbus/{device_name}/status - 设备状态
        - modbus/{device_name}/{tag} - 单个数据点
        """
        if not self.connected:
            logger.warning("Not connected to MQTT broker, skipping publish")
            return False
        
        device_name = device_data.get('device', 'unknown').replace(' ', '_')
        data = device_data.get('data', {})
        status = device_data.get('status', 'unknown')
        
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        # 1. 发布设备状态
        status_topic = f"{base_topic}/{device_name}/status"
        status_payload = json.dumps({
            'status': status,
            'timestamp': timestamp
        })
        self.client.publish(status_topic, status_payload, qos=1, retain=True)
        
        if not data:
            return False
        
        # 2. 发布完整遥测数据
        telemetry_topic = f"{base_topic}/{device_name}/telemetry"
        telemetry_payload = json.dumps({
            'device': device_data.get('device'),
            'device_type': device_data.get('device_type'),
            'unit_id': device_data.get('unit_id'),
            'timestamp': timestamp,
            'data': data
        }, ensure_ascii=False)
        
        result = self.client.publish(telemetry_topic, telemetry_payload, qos=1, retain=True)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.debug(f"Published to {telemetry_topic}: {len(data)} values")
        else:
            logger.error(f"Failed to publish to {telemetry_topic}")
            return False
        
        # 3. 发布单个数据点（便于订阅特定值）
        for tag, value in data.items():
            topic = f"{base_topic}/{device_name}/{tag}"
            payload = json.dumps({
                'value': value,
                'timestamp': timestamp
            })
            self.client.publish(topic, payload, qos=0, retain=True)
        
        return True