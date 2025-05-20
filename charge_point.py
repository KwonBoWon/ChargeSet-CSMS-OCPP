import asyncio
import datetime
import websockets

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

# TODO 함수 전체적으로 인자값들 조정
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
        print("BootNotification 응답:", response)

    async def send_heartbeat(self):
        request = call.Heartbeat()
        response = await self.call(request)
        print("heartbeat 응답:", response)

    async def send_authorize(self, _id_token: str = "token-3456"):
        request = call.Authorize(
            id_token={"id_token": _id_token, "type": "Central"}
        )
        response = await self.call(request)
        print("Authorize 응답:", response)
        return response

    async def start_transaction(
            self, _user_id: str = "token3456", _id_token:str = "token3456",
            _evse_id: str = 1, _connector_id: int = 1,
            _charging_schedules: List[Dict[str, Any]] = [{"start_period": 0, "charging_rate_unit": "W", "charging_rate": 0}],
            _start_time:str = '2025-04-14T13:00:00', _end_time:str = '2025-04-14T13:00:00'
    ):
        timestamp = datetime.now(timezone.utc).isoformat()
        _custom_data: Dict[str, Any] = {
            "vendor_id": "ChargeSet",  # 필수 필드를 추가
            'evse_id': _evse_id,
            'connector_id': _connector_id,
            "user_id": _user_id,
            "id_token": _id_token,
            "charging_schedules": _charging_schedules,
            'start_time': _start_time,
            'end_time': _end_time,
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
        print("Transaction Started 응답:", response)

    async def stop_transaction(
            self, _transaction_id: str = "tx-001" , _stopped_reason: str = "EVDisconnected",
            _evse_id: int = 1, _connector_id: int = 1
    ):
        timestamp = datetime.now(timezone.utc).isoformat()
        _custom_data:Dict[str, Any] = {
            "vendorId": "ChargeSet",  # 필수 필드를 추가
            "Test":"test"
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
        print("Transaction Ended 응답:", response)

async def run_cp(cp):
    try:
        await cp.start()
    except websockets.exceptions.ConnectionClosedOK:
        print("연결이 정상적으로 종료되었습니다.")

async def authorize_transaction_manager(cp):
    authorzie_response = await cp.send_authorize("token-1234") # TODO 토큰값 넘기기
    print("authorize_response:") # chargingSchedules 받음
    print(authorzie_response)
    _charging_schedules = authorzie_response.custom_data["charging_schedules"]
    _evse_id = authorzie_response.custom_data['evse_id']
    _user_id = authorzie_response.custom_data['user_id']
    _id_token = authorzie_response.custom_data['id_token']
    _connector_id = authorzie_response.custom_data['connector_id']
    _start_time = authorzie_response.custom_data['start_time']
    _end_time = authorzie_response.custom_data['end_time']

    await cp.start_transaction(
        _user_id, _id_token, _evse_id, _connector_id, _charging_schedules
    )
    for charging_schedule in _charging_schedules:
        print(f"charging_schedule: {charging_schedule}")
        charging_period=charging_schedule["start_period"]
        if charging_period != 0:
            await asyncio.sleep(charging_period/100)
        # TODO 트랜잭션 업데이트, 시간이 되면 보내야함..
    await cp.stop_transaction() # TODO트랜잭션 ended로 업데이트
    await asyncio.sleep(1)

async def charge_point_manager(uri, cp_name):
    async with websockets.connect(uri, subprotocols=["ocpp2.0.1"]) as ws:
        cp = ChargePoint201(cp_name, ws)
        asyncio.create_task(run_cp(cp))
        await asyncio.sleep(1)
        await cp.send_boot_notification()
        await asyncio.sleep(1)
        print(f"ChargeStation {cp_name} is ready to charge.")

        # TODO 여기에서 무한루프로 플러그앤 차지 기다리면 됨
        await authorize_transaction_manager(cp)
        # TODO 받아야 하는 데이터 evseId, connectorId, userId(token),
"""
        while True:
            command = await asyncio.to_thread(input, f"Enter command for {cp_name} (start/stop/exit): ")
            command = command.strip()
            if command == "start":
                print(f"Starting transaction for {cp_name}...")
                await cp.start_transaction()
            elif command == "stop":
                print(f"Stopping transaction for {cp_name}...")
                await cp.stop_transaction()
            elif command == "exit":
                print(f"Exiting {cp_name} management...")
                break
            else:
                print("Unknown command. Please use 'start', 'stop', or 'exit'.")
"""



async def main(*args, **kwargs):
    uri = "ws://localhost:9000/"
    # TODO main함수 인자로 처음 CP값 넘겨주면 될 것 같음
    await asyncio.gather(
        charge_point_manager(uri + "ST_001", "ST_001"),
        #charge_point_manager(uri + "ST_002", "ST_002"),
    )


# TODO 1분마다 데이터 최신화

if __name__ == "__main__":
    asyncio.run(main())