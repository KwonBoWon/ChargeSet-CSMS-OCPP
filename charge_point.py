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


class ChargePoint201(CP):
    def __init__(self, id, ws):
        super().__init__(id, ws)


    async def send_boot_notification(self):
        request = call.BootNotification(
            charging_station={
                "model": "Model X",
                "vendor_name": "Vendor Y"
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

    async def start_transaction(self):
        timestamp = datetime.now(timezone.utc).isoformat()
        request = call.TransactionEvent(
            event_type="Started",
            timestamp=timestamp,
            trigger_reason="Authorized",
            seq_no=1,
            transaction_info={"transaction_id": "tx-001"},
            id_token={"id_token": "token-3456", "type": "Central"},
            evse={"id": 1, "connector_id": 1}
        )
        response = await self.call(request)
        print("Transaction Started 응답:", response)



    async def stop_transaction(
            self, _transaction_id: str = "tx-001" , _stopped_reason: str = "EVDisconnected",
            _evse_id: int = 1, _connector_id: int = 1
    ):
        timestamp = datetime.now(timezone.utc).isoformat()
        request = call.TransactionEvent(
            event_type="Ended",
            timestamp=timestamp,
            trigger_reason="EVCommunicationLost",
            seq_no=2,
            transaction_info={
                "transaction_id": _transaction_id,
                "stopped_reason": _stopped_reason
            },
            evse={"id": _evse_id, "connector_id": _connector_id},
        )
        request.custom_data:Dict[str, Any] = {
            "vendorId": "ChargeSet",  # 필수 필드를 추가
            "Test":"test"
        }
        response = await self.call(request)
        print("Transaction Ended 응답:", response)

async def run_cp(cp):
    try:
        await cp.start()
    except websockets.exceptions.ConnectionClosedOK:
        print("연결이 정상적으로 종료되었습니다.")

async def authorize_transaction_manager(cp):
    while True:
        authorzie_response = await cp.send_authorize()
        print("authorize_response:") # chargingSchedules 받음
        print(authorzie_response)
        print(authorzie_response.custom_data)
        await asyncio.sleep(1)
        await cp.start_transaction()
        await asyncio.sleep(5) # 여기에 차지 스케쥴 계산하는거 넣으면됨
        await cp.stop_transaction()
        await asyncio.sleep(10)
        break

async def charge_point_manager(uri, cp_name):
    async with websockets.connect(uri, subprotocols=["ocpp2.0.1"]) as ws:
        cp = ChargePoint201(cp_name, ws)
        asyncio.create_task(run_cp(cp))
        await asyncio.sleep(1)
        await cp.send_boot_notification()
        await asyncio.sleep(1)

        print(f"ChargeStation {cp_name} is ready to charge.")
        await authorize_transaction_manager(cp)

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



async def main():
    uri = "ws://localhost:9000/"

    await asyncio.gather(
        charge_point_manager(uri + "CP_01", "CP_01"),
        #charge_point_manager(uri + "CP_02", "CP_02"),
    )




if __name__ == "__main__":
    asyncio.run(main())