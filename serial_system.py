import asyncio
import serial_asyncio
import serial.tools.list_ports
import json
import platform
import os

candidates = []

def get_usb_port_id(device):
    """
    /dev/ttyACM0 → /sys/class/tty/ttyACM0/device → realpath → 경로에서 USB 포트 ID (예: 1-1.3) 추출
    """
    try:
        basename = os.path.basename(device)
        realpath = os.path.realpath(f"/sys/class/tty/{basename}/device")
        segments = realpath.split('/')
        for segment in segments:
            if segment.startswith('1-'):  # 라즈베리파이 USB 허브 포트 패턴
                return segment
    except Exception as e:
        return f"unknown({e})"
    return "unknown"


class ESP32Protocol(asyncio.Protocol):
    def __init__(self, port):
        self.buffer = ""
        self.port = port
        self.port_id = get_usb_port_id(port.device)

    def connection_made(self, transport):
        self.transport = transport
        print(f"ESP{self.port.device} 연결됨 (포트 ID: {self.port_id}), HWID:{self.port.hwid}")

    def data_received(self, data):
        self.buffer += data.decode()
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            line = line.strip()
            print(f"수신된 ID Token: {line}")
            #self.handle_id_token(line)
    """
    def handle_id_token(self, id_token: str):
        print(f"처리 중인 ID Token: {id_token}")
        response = {
            "chargingSchedules": [
                {"startPeriod": 0, "limit": 4000, "useESS": True},
                {"startPeriod": 1800, "limit": 3000, "useESS": False}
            ]
        }
        json_str = json.dumps(response) + "\n"
        self.transport.write(json_str.encode())
        print("JSON 응답 전송 완료")
    """
    def connection_lost(self, exc):
        print(f"ESP{self.port.device} 연결 끊김")
        candidates.remove(self.port.device)

async def find_esp32_port():
    system = platform.system()

    print(f"ESP32 포트를 기다리는중 (OS:{system})")
    while True:
        ports = serial.tools.list_ports.comports()
        for port in ports:
            desc = port.description.lower()
            dev = port.device.lower()

            if system == "Darwin":  # macOS
                if "usbserial" in dev or "usbmodem" in dev or "cp210" in desc or "ch340" in desc:
                    if port.device not in candidates:
                        candidates.append(port.device)
                        print(port.device)
                        asyncio.create_task(connect_esp32(port))
            elif system == "Linux":
                if "ttyusb" in dev or "ttyacm" in dev:
                    if port.device not in candidates:
                        candidates.append(port.device)
                        print(port.device)
                        asyncio.create_task(connect_esp32(port))
        await asyncio.sleep(0.5)

async def connect_esp32(port):
    loop = asyncio.get_running_loop()
    await serial_asyncio.create_serial_connection(
        loop, lambda: ESP32Protocol(port), port.device, baudrate=115200
    )


async def main():
    await find_esp32_port()
    """
    loop = asyncio.get_running_loop()
    await serial_asyncio.create_serial_connection(
        loop, ESP32Protocol, port, baudrate=115200
    )
    """
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())