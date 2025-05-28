import asyncio
import datetime
import websockets
import asyncio
import serial_asyncio
import serial.tools.list_ports
import json
import platform
import logging
import re
import os

from dotenv import load_dotenv
from ocpp.v201 import ChargePoint as CP
from ocpp.v201 import call, call_result
from ocpp.routing import on
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from ocpp.v201.enums import (
    Action,
    RegistrationStatusEnumType,
    AuthorizationStatusEnumType,
    AttributeEnumType,
    NotifyEVChargingNeedsStatusEnumType,
    GenericStatusEnumType,
    Iso15118EVCertificateStatusEnumType
)
def extract_port_number(location: str) -> str:
    match = re.search(r'\d-\d\.(\d):\d', location)
    return match.group(1) if match else "?"

candidates = [] # 현재 usb 포트

class ColorFormatter2(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[94m",    # 파랑
        logging.INFO: "\033[92m",     # 초록
        logging.WARNING: "\033[93m",  # 노랑
        logging.ERROR: "\033[91m",    # 빨강
        logging.CRITICAL: "\033[95m", # 보라
    }
    RESET = "\033[0m"

    def format(self, record):
        log_color = self.COLORS.get(record.levelno, self.RESET)
        message = super().format(record)
        return f"{log_color}{message}{self.RESET}"


# 색상 적용
for handler in logging.getLogger().handlers:
    handler.setFormatter(ColorFormatter2(handler.formatter._fmt))

#logging.basicConfig(level=logging.INFO)
# 전역 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

class ChargePoint201(CP):
    def __init__(self, id, ws):
        super().__init__(id, ws)

    async def send_boot_notification(self):
        request = call.BootNotification(
            charging_station={
                "model": "CapStone",
                "vendor_name": "ChargeSet"
            },
            reason="PowerUp"
        )
        response = await self.call(request)
        logging.info(f"Send a BootNotification")
        logging.info(f"Received a BootNotification")

    async def send_heartbeat(self):
        request = call.Heartbeat()
        response = await self.call(request)
        logging.info("Send a Heartbeat")

    async def send_authorize(self, _id_token: str = "token-3456"):
        request = call.Authorize(
            id_token={"id_token": _id_token, "type": "Central"}
        )
        response = await self.call(request)
        logging.info(f"Send a Authorize: {request.id_token}")
        logging.info(f"Received a Authorize")
        return response

    async def start_transaction(
            self, _user_id: str = "token3456", _id_token:str = "token3456",
            _evse_id: str = 1, _connector_id: int = 1,
            _reservation_id: str = "res-001",
            _charging_schedules: List[Dict[str, Any]] = [{"start_period": 0, "charging_rate_unit": "W", "charging_rate": 0}],
            _start_time:str = '2025-04-14T13:00:00', _end_time:str = '2025-04-14T13:00:00',
            _cost: int = 1333, _energyWh: int=886787979
    ):
        timestamp = datetime.now(timezone.utc).isoformat()
        _custom_data: Dict[str, Any] = {
            "vendor_id": "ChargeSet",  # 필수 필드를 추가
            'evse_id': _evse_id,
            'connector_id': _connector_id,
            "user_id": _user_id,
            "id_token": _id_token,
            "reservation_id": _reservation_id,
            "charging_schedules": _charging_schedules,
            'start_time': _start_time,
            'end_time': _end_time,
            'cost': _cost,
            'energyWh': _energyWh,
        }
        request = call.TransactionEvent(
            event_type="Started",
            timestamp=timestamp,
            trigger_reason="Authorized",
            seq_no=1,
            transaction_info={
                "transaction_id": "tx-001",
            },
            evse={"id": _connector_id, "connector_id": _connector_id},
            custom_data=_custom_data
        )

        response = await self.call(request)
        logging.info(f"Send a Transaction Started: {request.event_type}")
        logging.info(f"Received a Transaction Started")

    async def stop_transaction(
            self, _transaction_id: str = "tx-001" , _stopped_reason: str = "EVDisconnected",
            _evse_id: str = "st", _connector_id: int = 1, _reservation_id: str = "res-001", _id_token:str = "token3456"
    ):
        timestamp = datetime.now(timezone.utc).isoformat()
        _custom_data:Dict[str, Any] = {
            "vendorId": "ChargeSet",  # 필수 필드를 추가
            "userID":_id_token,
            "evseId": _evse_id,
            "connectorId": _connector_id,
            "reservationId": _reservation_id,
        }
        request = call.TransactionEvent(
            event_type="Ended",
            timestamp=timestamp,
            trigger_reason="EVCommunicationLost",
            seq_no=2,
            transaction_info={
                "transaction_id": _transaction_id,
                "stopped_reason": _stopped_reason
            },
            evse={"id": _connector_id, "connector_id": _connector_id},
            custom_data=_custom_data
        )
        response = await self.call(request)
        logging.info(f"Send a Transaction Ended: {request.event_type}")
        logging.info(f"Received a Transaction Ended")


    async def cost_energy_updated(
            self, reservation_id: str = "tx-001",
            _total_cost: float = 222, _total_energy:float = 22
    ):
        logging.info(f"Cost Updated: {_total_cost} KRW")
        logging.info(f"Energy Updated: {_total_energy} Wh")
        _custom_data: Dict[str, Any] = {
            "vendorId": "ChargeSet",  # 필수 필드를 추가
            "reservationId": reservation_id,
            "totalEnergy": _total_energy,
        }
        request = call.CostUpdated(
            total_cost=_total_cost,
            transaction_id="tx-001",
            custom_data=_custom_data
        )
        response = await self.call(request)
        logging.info(f"Send a CostUpdated: {request.total_cost}")

async def run_cp(cp):
    try:
        await cp.start()
    except websockets.exceptions.ConnectionClosedOK:
        logging.info("Disconnected from CSMS. Shutting down ChargePointManager.")

async def sleep_in_chunks(total_duration, chunk_size=10):
    remaining = total_duration
    while remaining > 0:
        sleep_time = min(chunk_size, remaining)
        await asyncio.sleep(sleep_time)
        remaining -= sleep_time

async def authorize_transaction_manager(cp, id_token: str = "token-1234", transport=None):
    authorzie_response = await cp.send_authorize(id_token)

    if authorzie_response.id_token_info['status'] is not "Accepted":
        logging.error(f"Authorize Failed: {authorzie_response.id_token_info['status']}")
        # 에러 전송
        response = {
            "error": authorzie_response.id_token_info['status']
        }
        json_str = json.dumps(response) + "\n"
        transport.write(json_str.encode())
        return



    _charging_schedules = authorzie_response.custom_data["charging_schedules"]
    _evse_id = authorzie_response.custom_data['evse_id']
    _user_id = authorzie_response.custom_data['user_id']
    _id_token = authorzie_response.custom_data['id_token']
    _connector_id = authorzie_response.custom_data['connector_id']
    _start_time = authorzie_response.custom_data['start_time']
    _end_time = authorzie_response.custom_data['end_time']
    _reservation_id = authorzie_response.custom_data['reservation_id']
    _cost = authorzie_response.custom_data['cost']
    _energyWh = authorzie_response.custom_data['target_energy_wh']

    # 스케쥴 전송
    response = {
        "chargingSchedules": _charging_schedules
    }
    json_str = json.dumps(response) + "\n"
    transport.write(json_str.encode())


    await cp.start_transaction(
        _user_id, _id_token,
        _evse_id, _connector_id,
        _reservation_id, _charging_schedules,
        _start_time, _end_time,
        _cost, _energyWh
    )
    last_period = 0
    last_limit = 0
    now_cost = 0.0
    now_energy = 0.0
    for charging_schedule in _charging_schedules:
        charging_period=charging_schedule["start_period"]
        charging_limit=charging_schedule["limit"]
        if charging_period != 0:
            remaining = charging_period-last_period
            while remaining > 0:
                sleep_time = min(12, remaining)
                await asyncio.sleep(sleep_time)
                remaining -= sleep_time
                if last_limit >= 60000:
                    now_cost += 72
                    now_energy += 200
                else:
                    now_cost += 6
                    now_energy += 20

                await cp.cost_energy_updated(_reservation_id, now_cost, now_energy)

            last_period=charging_period
            last_limit=charging_limit
            if charging_limit == 0:
                await cp.stop_transaction(
                    "tx-001", "EVDisconnected", _evse_id, _connector_id, _reservation_id, _id_token
                )
    await asyncio.sleep(1)

class ESP32Protocol(asyncio.Protocol):
    def __init__(self, port, cp):
        self.buffer = ""
        self.port = port
        self.cp = cp
        self.portNumber = extract_port_number(port.location)

    def connection_made(self, transport):
        self.transport = transport
        logging.info(f"[EV] {self.port.device} connected, PortNumber:{self.portNumber}")
        # TODO: 커넥터 아이디(혹은 evseID) 넘겨서(혹은 예약데이터랑 비교해서) 예외처리

    def data_received(self, data):
        self.buffer += data.decode()
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            line = line.strip()
            logging.info(f"[EV] Received ID Token: {line}")
            asyncio.create_task(authorize_transaction_manager(self.cp, line, self.transport))

    def connection_lost(self, exc):
        logging.info(f"[EV] {self.port.device} Disconnected")
        candidates.remove(self.port.device)

async def find_esp32_port(cp):
    system = platform.system()

    logging.info(f"[EV] port waiting... (OS:{system})")
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
                        asyncio.create_task(connect_esp32(port,cp))
            elif system == "Linux":
                if "ttyusb" in dev or "ttyacm" in dev:
                    if port.device not in candidates:
                        candidates.append(port.device)
                        print(port.device)
                        asyncio.create_task(connect_esp32(port, cp))
        await asyncio.sleep(0.5)

async def connect_esp32(port, cp):
    loop = asyncio.get_running_loop()
    await serial_asyncio.create_serial_connection(
        loop, lambda: ESP32Protocol(port, cp), port.device, baudrate=115200
    )

async def charge_point_manager(uri, cp_name):
    async with websockets.connect(uri, subprotocols=["ocpp2.0.1"]) as ws:
        cp = ChargePoint201(cp_name, ws)
        asyncio.create_task(run_cp(cp))
        await asyncio.sleep(1)
        await cp.send_boot_notification()
        await asyncio.sleep(1)
        logging.info(f"ChargeStation {cp_name} is ready to charge.")
        await find_esp32_port(cp)

async def main(*args, **kwargs):
    load_dotenv()
    uri = os.getenv("CSMS_URI")

    #uri = "ws://192.168.35.95:9000/"
    await asyncio.gather(
        charge_point_manager(uri + "ST-001", "ST-001"),
        #charge_point_manager(uri + "ST-002", "ST-002"),
    )

if __name__ == "__main__":
    asyncio.run(main())