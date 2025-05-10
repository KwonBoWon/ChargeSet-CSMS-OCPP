import asyncio
import datetime
import websockets
import websockets_test

from ocpp.v201 import ChargePoint as CP
from ocpp.v201 import call, call_result
from ocpp.routing import on
from datetime import datetime, timezone
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

    @on('GetVariables')
    async def on_get_variables(self, get_variable_data, **kwargs):
        print("GetVariables 요청 수신:", get_variable_data)
        return call_result.GetVariables(
            get_variable_result=[{
                "attribute_status": "Accepted",
                "attribute_type": "Actual",
                "value": "42",
                "component": {"name": "ComponentX"},
                "variable": {"name": "VariableY"}
            }]
        )
    @on('request_start_transaction_req')
    async def on_request_start_transaction_req(self, start_transaction_req, **kwargs):
        print("request start transaction")
        return

    @on(Action.heartbeat)
    async def on_heartbeat_req(self, heartbeat_req, **kwargs):
        print("heartbeat req응답")
        await self.send_heartbeat()
        return

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

    async def send_authorize(self):
        request = call.Authorize(
            id_token={
                "id_token": "token-3456",
                "type": "Central"
            }
        )
        response = await self.call(request)
        print("Authorize 응답:", response)

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

    async def send_meter_values(self):
        timestamp = datetime.now(timezone.utc).isoformat()
        request = call.MeterValues(
            evse_id=1,
            meter_value=[{
                "timestamp": timestamp,
                "sampled_value": [{
                    "value": "15.2",
                    "measurand": "Energy.Active.Import.Register"
                }]
            }]
        )
        response = await self.call(request)
        print("MeterValues 응답:", response)

    async def stop_transaction(self):
        timestamp = datetime.now(timezone.utc).isoformat()
        request = call.TransactionEvent(
            event_type="Ended",
            timestamp=timestamp,
            trigger_reason="EVCommunicationLost",
            seq_no=2,
            transaction_info={
                "transaction_id": "tx-001",
                "stopped_reason": "EVDisconnected"
            },
            evse={"id": 1, "connector_id": 1}
        )
        response = await self.call(request)
        print("Transaction Ended 응답:", response)

async def run_cp(cp):
    try:
        await cp.start()
    except websockets_test.exceptions.ConnectionClosedOK:
        print("연결이 정상적으로 종료되었습니다.")

async def authorize_transaction(cp):
    try:
        await asyncio.sleep(1)
        await cp.send_authorize()
        await asyncio.sleep(1)
    except Exception as e:
        print(f"An error occurred in authorize_transaction: {e}")




async def main():
    uri = "ws://localhost:9000/CP_01"

    async with websockets_test.connect(uri, subprotocols=["ocpp2.0.1"]) as ws:
        cp = ChargePoint201("CP_01", ws)

        asyncio.create_task(run_cp(cp))

        await asyncio.sleep(1)
        await cp.send_boot_notification()
        await asyncio.sleep(1)
        await cp.send_authorize()
        await asyncio.sleep(1)
        """
        await cp.start_transaction()
        await asyncio.sleep(5)
        await cp.stop_transaction()
        await asyncio.sleep(10)
        """
"""
    async with websockets.connect(uri, subprotocols=["ocpp2.0.1"]) as ws:
        cp2 = ChargePoint201("CP_02", ws)

        asyncio.create_task(run_cp(cp2))

        await asyncio.sleep(1)
        await cp.send_boot_notification()
        await asyncio.sleep(1)
        await cp.send_authorize()
        await asyncio.sleep(1)
"""



if __name__ == "__main__":
    asyncio.run(main())