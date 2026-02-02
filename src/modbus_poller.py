"""使用 pymodbus 轮询 Modbus 设备"""
import logging
import struct
import threading
import time
from typing import Optional, Dict, Any, List
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from src.config_parser import ModbusDevice, ModbusRegister

logger = logging.getLogger(__name__)


class ModbusPoller:
    """Modbus 数据轮询器"""
    
    def __init__(self):
        self.clients: Dict[str, ModbusSerialClient] = {}
        self.locks: Dict[str, threading.Lock] = {}  # 串口访问锁
        self.client_create_lock = threading.Lock()  # 创建客户端的全局锁
    
    def get_client(self, device: ModbusDevice) -> ModbusSerialClient:
        """获取或创建 Modbus 客户端（线程安全）"""
        key = f"{device.port}_{device.baudrate}_{device.parity}"
        
        # 使用全局锁保护客户端创建过程，避免重复创建
        with self.client_create_lock:
            if key not in self.clients:
                logger.info(f"Creating Modbus client for {device.port} "
                           f"({device.baudrate}, {device.parity}, {device.stopbits}, {device.bytesize})")
                
                client = ModbusSerialClient(
                    port=device.port,
                    baudrate=device.baudrate,
                    parity=device.parity,
                    stopbits=device.stopbits,
                    bytesize=device.bytesize,
                    timeout=device.timeout
                )
                
                if not client.connect():
                    logger.error(f"Failed to connect to {device.port}")
                    return None
                
                self.clients[key] = client
                self.locks[key] = threading.Lock()  # 为每个串口创建锁
                logger.info(f"Connected to {device.port}")
        
        return self.clients[key]
    
    def read_register(self, client: ModbusSerialClient, device: ModbusDevice, 
                     register: ModbusRegister) -> Optional[float]:
        """读取单个寄存器"""
        try:
            # 根据功能码选择读取方法
            if register.function_code == 1:
                # Read Coils
                result = client.read_coils(register.address, register.count, 
                                          slave=device.unit_id)
            elif register.function_code == 2:
                # Read Discrete Inputs
                result = client.read_discrete_inputs(register.address, register.count, 
                                                    slave=device.unit_id)
            elif register.function_code == 3:
                # Read Holding Registers
                result = client.read_holding_registers(register.address, register.count, 
                                                      slave=device.unit_id)
            elif register.function_code == 4:
                # Read Input Registers
                result = client.read_input_registers(register.address, register.count, 
                                                    slave=device.unit_id)
            else:
                logger.error(f"Unsupported function code: {register.function_code}")
                return None
            
            # 检查响应
            if result.isError():
                logger.warning(f"Modbus error reading {device.name}/{register.tag}: {result}")
                return None
            
            # 解析数据
            if register.function_code in [1, 2]:
                # Coils/Discrete Inputs
                return float(result.bits[0])
            else:
                # Registers
                return self._decode_registers(result.registers, register, device)
        
        except ModbusException as e:
            logger.error(f"Modbus exception reading {device.name}/{register.tag}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading {device.name}/{register.tag}: {e}", exc_info=True)
            return None
    
    def _decode_registers(self, registers: List[int], register: ModbusRegister, 
                         device: ModbusDevice) -> Optional[float]:
        """解码寄存器数据"""
        try:
            # 检查寄存器数据完整性
            if len(registers) < register.count:
                logger.warning(f"Incomplete register data: expected {register.count}, got {len(registers)}")
                return None
            
            # 确定字节序
            byte_order = '>' if device.byte_order == 'BIG' else '<'
            word_order = device.word_order
            
            # 单个寄存器
            if register.count == 1:
                if register.data_type == 'uint16':
                    value = int(registers[0])  # 确保是整数类型
                elif register.data_type == 'int16':
                    value = struct.unpack(f'{byte_order}h', struct.pack(f'{byte_order}H', registers[0]))[0]
                else:
                    value = registers[0]
            
            # 两个寄存器（32位）
            elif register.count == 2:
                if word_order == 'BIG':
                    raw = (registers[0] << 16) | registers[1]
                else:
                    raw = (registers[1] << 16) | registers[0]
                
                if register.data_type == 'uint32':
                    value = raw
                elif register.data_type == 'int32':
                    value = struct.unpack(f'{byte_order}i', struct.pack(f'{byte_order}I', raw))[0]
                elif register.data_type == 'float32':
                    bytes_data = struct.pack(f'{byte_order}I', raw)
                    value = struct.unpack(f'{byte_order}f', bytes_data)[0]
                else:
                    value = raw
            
            # 四个寄存器（64位）
            elif register.count == 4:
                if word_order == 'BIG':
                    raw = (registers[0] << 48) | (registers[1] << 32) | (registers[2] << 16) | registers[3]
                else:
                    raw = (registers[3] << 48) | (registers[2] << 32) | (registers[1] << 16) | registers[0]
                
                if register.data_type == 'uint64':
                    value = raw
                elif register.data_type == 'int64':
                    value = struct.unpack(f'{byte_order}q', struct.pack(f'{byte_order}Q', raw))[0]
                elif register.data_type == 'float64':
                    bytes_data = struct.pack(f'{byte_order}Q', raw)
                    value = struct.unpack(f'{byte_order}d', bytes_data)[0]
                else:
                    value = raw
            else:
                logger.warning(f"Unsupported register count: {register.count}")
                return None
            
            # 应用缩放（保持数据类型）
            return register.apply_scaling(value)
        
        except Exception as e:
            logger.error(f"Error decoding registers: {e}", exc_info=True)
            return None
    
    def poll_device(self, device: ModbusDevice) -> Dict[str, Any]:
        """轮询设备所有寄存器"""
        client = self.get_client(device)
        if not client:
            return {
                'device': device.name,
                'device_type': device.device_type,
                'unit_id': device.unit_id,
                'status': 'disconnected',
                'data': {}
            }
        
        # 使用锁保护串口访问，避免多设备并发冲突
        key = f"{device.port}_{device.baudrate}_{device.parity}"
        with self.locks[key]:
            data = {}
            success_count = 0
            
            for register in device.registers:
                value = self.read_register(client, device, register)
                if value is not None:
                    data[register.tag] = value
                    success_count += 1
                
                # 寄存器读取间添加延迟，避免设备响应不及
                time.sleep(0.08)  # 80ms延迟，给设备更多处理时间
        
        logger.info(f"Polled {device.name}: {success_count}/{len(device.registers)} registers")
        
        return {
            'device': device.name,
            'device_type': device.device_type,
            'unit_id': device.unit_id,
            'status': 'connected' if success_count > 0 else 'error',
            'data': data
        }
    
    def close_all(self):
        """关闭所有连接"""
        for key, client in self.clients.items():
            logger.info(f"Closing connection: {key}")
            client.close()
        self.clients.clear()