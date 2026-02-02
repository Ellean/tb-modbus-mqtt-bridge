"""解析 ThingsBoard Gateway 配置并转换为 Modbus 参数"""
import json
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModbusRegister:
    """Modbus 寄存器定义"""
    tag: str
    address: int
    function_code: int
    count: int
    data_type: str
    divider: float = 1.0
    multiplier: float = 1.0
    
    def needs_scaling(self) -> bool:
        """检查是否需要应用缩放"""
        return self.multiplier != 1.0 or self.divider != 1.0
    
    def is_integer_type(self) -> bool:
        """检查是否为整数类型"""
        return self.data_type in ('uint16', 'int16', 'uint32', 'int32', 'uint64', 'int64')
    
    def apply_scaling(self, value):
        """应用缩放因子，保持整数类型"""
        if not self.needs_scaling():
            return value  # 不需要缩放，保持原始类型
        
        result = (value * self.multiplier) / self.divider
        
        # 如果是整数类型且结果是整数值，返回整数
        if self.is_integer_type() and result == int(result):
            return int(result)
        return result


@dataclass
class ModbusDevice:
    """Modbus 设备定义"""
    name: str
    device_type: str
    unit_id: int
    port: str
    baudrate: int
    parity: str
    stopbits: int
    bytesize: int
    timeout: float
    poll_period: int  # ms
    byte_order: str = "BIG"
    word_order: str = "BIG"
    registers: List[ModbusRegister] = field(default_factory=list)
    
    @property
    def poll_interval(self) -> float:
        """轮询间隔（秒）"""
        return self.poll_period / 1000.0


class ConfigParser:
    """配置解析器"""
    
    # ThingsBoard 数据类型映射
    TYPE_MAPPING = {
        '16uint': ('uint16', 1),
        '16int': ('int16', 1),
        '32uint': ('uint32', 2),
        '32int': ('int32', 2),
        '32float': ('float32', 2),
        'float': ('float32', 2),
        'double': ('float64', 4),
        '64int': ('int64', 4),
        '64uint': ('uint64', 4),
    }
    
    @staticmethod
    def parse_thingsboard_config(config_path: str) -> List[ModbusDevice]:
        """解析 ThingsBoard Gateway 配置文件"""
        logger.info(f"Parsing config: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        devices = []
        connector_name = config.get('name', 'Unknown')
        
        for slave in config['master']['slaves']:
            registers = []
            
            # 解析 attributes（属性）
            for attr in slave.get('attributes', []):
                reg = ConfigParser._parse_register(attr)
                if reg:
                    registers.append(reg)
            
            # 解析 timeseries（时序数据）
            for ts in slave.get('timeseries', []):
                reg = ConfigParser._parse_register(ts)
                if reg:
                    registers.append(reg)
            
            if registers:
                device = ModbusDevice(
                    name=slave.get('deviceName', f"Device_{slave['unitId']}"),
                    device_type=slave.get('deviceType', 'Unknown'),
                    unit_id=slave['unitId'],
                    port=slave['port'],
                    baudrate=slave.get('baudrate', 9600),
                    parity=ConfigParser._parse_parity(slave.get('parity', 'N')),
                    stopbits=slave.get('stopbits', 1),
                    bytesize=slave.get('bytesize', 8),
                    timeout=slave.get('timeout', 35) / 1000.0,  # ms to seconds
                    poll_period=slave.get('pollPeriod', 1000),
                    byte_order=slave.get('byteOrder', 'BIG'),
                    word_order=slave.get('wordOrder', 'BIG'),
                    registers=registers
                )
                devices.append(device)
                logger.info(f"Loaded device '{device.name}' with {len(registers)} registers from {connector_name}")
            else:
                logger.warning(f"Device '{slave.get('deviceName')}' has no registers, skipping")
        
        return devices
    
    @staticmethod
    def _parse_register(reg_config: Dict[str, Any]) -> ModbusRegister:
        """解析单个寄存器配置"""
        try:
            data_type = reg_config.get('type', '16uint')
            mapped_type, default_count = ConfigParser.TYPE_MAPPING.get(
                data_type, ('uint16', 1)
            )
            
            return ModbusRegister(
                tag=reg_config['tag'],
                address=reg_config['address'],
                function_code=reg_config['functionCode'],
                count=reg_config.get('objectsCount', default_count),
                data_type=mapped_type,
                divider=float(reg_config.get('divider', 1.0)),
                multiplier=float(reg_config.get('multiplier', 1.0))
            )
        except Exception as e:
            logger.error(f"Failed to parse register config: {e}")
            return None
    
    @staticmethod
    def _parse_parity(parity: str) -> str:
        """解析校验位"""
        parity_map = {
            'N': 'N',
            'E': 'E',
            'O': 'O',
            'none': 'N',
            'even': 'E',
            'odd': 'O'
        }
        return parity_map.get(parity, 'N')