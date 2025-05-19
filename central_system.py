import logging
from datetime import datetime
import sys


import os
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional


from ocpp.routing import on
from ocpp.v201 import ChargePoint as cp
from ocpp.v201 import call, call_result
from ocpp.v201.datatypes import IdTokenInfoType, SetVariableDataType, GetVariableDataType, ComponentType, VariableType
from ocpp.v201.enums import (
    Action,
    RegistrationStatusEnumType,
    AuthorizationStatusEnumType,
    AttributeEnumType,
    NotifyEVChargingNeedsStatusEnumType,
    GenericStatusEnumType,
    Iso15118EVCertificateStatusEnumType
)
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)

load_dotenv()

mongodb_uri = os.getenv("MONGODB_URI")

client = MongoClient(mongodb_uri)
#clinet = MongoClient('localhost', 27017)
# TODO find_one, update_one 정렬하고 가장 나중값으로 사용해야함
db = client["charge-set"]
reservation_collection = db["reservation"]
charging_profile_collection = db["chargingProfile"]
transaction_collection = db["transaction"]
evse_collection = db["evse"]

class ChargePointHandler(cp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.charge_point_id = args[0]
        print("charge point id:", self.charge_point_id)

    @on(Action.boot_notification)
    async def on_boot_notification(self, **kwargs):
        print("boot notification")
        print(kwargs)
        logging.debug("Received a BootNotification")
        # evse 값 업데이트
        evse_collection.update_many({"stationId": self.charge_point_id},
                                    {"$set": {"evseStatus": "AVAILABLE", "lastUpdated": datetime.now()}})

        return call_result.BootNotification(current_time=datetime.now().isoformat(),
                                                   interval=300, status=RegistrationStatusEnumType.accepted)

    # 연결 끊어질 때
    async def close_connection(self):
        # evse 값 업데이트
        evse_collection.update_many({"stationId": self.charge_point_id},
                                    {"$set": {"evseStatus": "OFFLINE", "lastUpdated": datetime.now()}})

    @on(Action.status_notification)
    def on_status_notification(self, **kwargs):
        return call_result.StatusNotification()

    @on(Action.heartbeat)
    def on_heartbeat(self, **kwargs):
        print("heartbeat")
        print(kwargs)
        return call_result.Heartbeat(current_time=datetime.utcnow().isoformat())

    # DB에서 예약정보 확인하고 인증 성공/실패
    # 2. stationID 맞는지
    # 3. connectorId 맞는지
    # 4. startTime맞는지
    # 5. reservation컬렉션 update waiting->active

    @on(Action.authorize)
    def on_authorize(self, **kwargs):
        print("Authorize")
        print(kwargs)
        authorize_id_token = kwargs["id_token"]["id_token"]
        reservation_data = reservation_collection.find_one({"idToken": authorize_id_token})

        print(reservation_data)

        if reservation_data is None:
            print("reservation not found")
            call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.no_credit))
            return call_result_authorize
        # TODO: 충전소 위치 확인, 커넥터 확인, 스타트타임 확인 -> 업데이트 해줘야함(예약시간 지남)


        match reservation_data["reservationStatus"]:
            case "ACTIVE": # "ACTIVE" -	현재 유효한 예약. 아직 예약된 시간이 아님 (예약을 생성하면 ACTIVE 상태)
                print("reservation already active")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.not_at_this_time))
            case "WAITING": # “WAITING”-	예약된 시간이 되었지만 아직 연결하지 않음(기다려주는 시간 10분이 지나지 않음)
                print("reservation waiting-accepted")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.accepted))
            case "ONGOING": # "ONGOING" -	예약 시간에 도달했고, 예약자 본인이 충전 중임
                print("reservation ongoing")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.concurrent_tx))
            case "EXPIRED": # "EXPIRED" -	예약 시간이 지났고, 실제 사용(충전)을 하지 않음 (노쇼)
                print("reservation expired")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.expired))
            case "COMPLETED": # "COMPLETED" -	예약자가 충전을 정상적으로 수행했고, 충전이 완료됨
                print("reservation completed")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.concurrent_tx))
            case "CANCELLED": # "CANCELLED" -	사용자가 직접 예약을 취소함
                print("reservation cancelled")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.invalid))
            case _: # 그외 값
                print("unknown error")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.unknown))


        reservation_id = str(reservation_data["_id"])  # 예약 id
        print(reservation_id)
        print("chargingProfile found")
        charging_profile:Dict[str, Any] = charging_profile_collection.find_one({"reservationId": reservation_id})["chargingSchedules"]
        print(charging_profile)

        _custom_data: Dict[str, Any] = {
            "vendorId": "ChargeSet",  # 필수 필드를 추가
            "chargingSchedules": charging_profile
        }

        call_result_authorize.custom_data = _custom_data
        return call_result_authorize



    @on(Action.set_charging_profile)
    def on_set_charging_profile(self, **kwargs):
        return call_result.SetChargingProfile(status=GenericStatusEnumType.accepte, charging_profile_id=1, custom_data=[Dict[str, Any]])


    @on(Action.transaction_event)
    def on_transaction_event(self, **kwargs):
        print("Transaction event")
        print(kwargs)
        # TODO evse값 업데이트, transaction 컬렉션에 값 업데이트
        if kwargs["event_type"] == "Started":
            transaction_collection.insert_one({
                "stationId": self.charge_point_id,#
                "evseId": "EVSE-ST1-001",#kwargs["evse_id"],#
                "connectorId": 1,#kwargs["connector_id"], #
                "userId": "user1234",# 이건 검색해야함;
                "idToken": "token-3456",#kwargs["id_token"],
                "reservationId": "67fb7450fcb584c29e147773",#kwargs["reservation_id"],#
                "startTime":datetime.now(),
                "endTime":"",
                "energyWh": "10000",
                "cost": 3100,
                "transactionStatus":"CHARGING",
                "startSchedule": datetime.now(),
                "chargingProfileSnapshots": "Array" #kwargs["charging_schedules"]
            })
        if kwargs["event_type"] == "Ended":
            transaction_collection.update_one({"transactionId":kwargs["transaction_id"]},{"$set":{"transactionStatus":"COMPLETE"}})
        if kwargs["event_type"] == "Update":
            pass
        return call_result.TransactionEvent()

    @on(Action.notify_charging_limit)
    def on_notify_charging_limit(self, **kwargs):
        return call_result.NotifyChargingLimit()

    @on(Action.notify_ev_charging_needs)
    def on_notify_ev_charging_needs(self, **kwargs):
        return call_result.NotifyEVChargingNeeds(status=NotifyEVChargingNeedsStatusEnumType.accepted)

    @on(Action.notify_ev_charging_schedule)
    def on_notify_ev_charging_schedule(self, **kwargs):
        return call_result.NotifyEVChargingSchedule(status=GenericStatusEnumType.accepted)

    @on(Action.report_charging_profiles)
    def on_report_charging_profiles(self, **kwargs):
        return call_result.ReportChargingProfiles()

    @on(Action.reservation_status_update)
    def on_reservation_status_update(self, **kwargs):
        return call_result.ReservationStatusUpdate()

    @on(Action.security_event_notification)
    def on_security_event_notification(self, **kwargs):
        return call_result.SecurityEventNotification()

    @on(Action.sign_certificate)
    def on_sign_certificate(self, **kwargs):
        return call_result.SignCertificate(status=GenericStatusEnumType.accepted)

    @on(Action.get_certificate_status)
    def on_get_certificate_status(self, **kwargs):
        return call_result.GetCertificateStatus(status=GenericStatusEnumType.accepted,
                                                       ocsp_result="IS_FAKED")

    @on(Action.data_transfer)
    def on_data_transfer(self, **kwargs):
        return call_result.DataTransfer(status=GenericStatusEnumType.accepted, data="")

    async def reset_req(self, **kwargs):
        payload = call.Reset(**kwargs)
        return await self.call(payload)

    async def request_start_transaction_req(self, **kwargs):
        print("request start transaction req")
        payload = call.RequestStartTransaction(**kwargs)
        return await self.call(payload)

    async def request_stop_transaction_req(self, **kwargs):
        payload = call.RequestStopTransaction(**kwargs)
        return await self.call(payload)

    async def change_availablility_req(self, **kwargs):
        payload = call.ChangeAvailability(**kwargs)
        return await self.call(payload)

    async def clear_cache_req(self, **kwargs):
        payload = call.ClearCache(**kwargs)
        return await self.call(payload)

    async def cancel_reservation_req(self, **kwargs):
        payload = call.CancelReservation(**kwargs)
        return await self.call(payload)

    async def certificate_signed_req(self, **kwargs):
        payload = call.CertificateSigned(**kwargs)
        return await self.call(payload)

    async def clear_charging_profile_req(self, **kwargs):
        payload = call.ClearChargingProfile(**kwargs)
        return await self.call(payload)

    async def clear_display_message_req(self, **kwargs):
        payload = call.ClearDisplayMessage(**kwargs)
        return await self.call(payload)

    async def clear_charging_limit_req(self, **kwargs):
        payload = call.ClearedChargingLimit(**kwargs)
        return await self.call(payload)

    async def clear_variable_monitoring_req(self, **kwargs):
        payload = call.ClearVariableMonitoringd(**kwargs)
        return await self.call(payload)

    async def cost_update_req(self, **kwargs):
        payload = call.CostUpdated(**kwargs)
        return await self.call(payload)

    async def customer_information_req(self, **kwargs):
        payload = call.CustomerInformation(**kwargs)
        return await self.call(payload)

    async def get_charging_profiles_req(self, **kwargs):
        payload = call.GetChargingProfiles(**kwargs)
        return await self.call(payload)

    async def get_log_req(self, **kwargs):
        payload = call.GetLog(**kwargs)
        return await self.call(payload)

    async def get_transaction_status_req(self, **kwargs):
        payload = call.GetTransactionStatus(**kwargs)
        return await self.call(payload)

    async def reserve_now_req(self, **kwargs):
        payload = call.ReserveNow(**kwargs)
        return await self.call(payload)

    async def send_local_list_req(self, **kwargs):
        payload = call.SendLocalList(**kwargs)
        return await self.call(payload)

    async def set_charging_profile_req(self, **kwargs):
        payload = call.SetChargingProfile(**kwargs)
        return await self.call(payload)

    async def set_display_message_req(self, **kwargs):
        payload = call.SetDisplayMessage(**kwargs)
        return await self.call(payload)

    async def trigger_message_req(self, **kwargs):
        payload = call.TriggerMessage(**kwargs)
        return await self.call(payload)

    async def unlock_connector_req(self, **kwargs):
        payload = call.UnlockConnector(**kwargs)
        return await self.call(payload)

    async def heartbeat_req(self, **kwargs):
        print("heartbeat req")
        payload = call.Heartbeat(**kwargs)
        return await self.call(payload)
