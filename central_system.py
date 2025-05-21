import logging
from datetime import datetime
import sys


import os

from bson import ObjectId
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

class ColorFormatter(logging.Formatter):
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
    handler.setFormatter(ColorFormatter(handler.formatter._fmt))

#logging.basicConfig(level=logging.INFO)
# 전역 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
# 환경설정
load_dotenv()

mongodb_uri = os.getenv("MONGODB_URI")

client = MongoClient(mongodb_uri)
db = client["charge-set"]
reservation_collection = db["reservation"]
charging_profile_collection = db["chargingProfile"]
transaction_collection = db["transaction"]
evse_collection = db["evse"]

class ChargePointHandler(cp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.charge_point_id = args[0]
        print("Connected charge point id:", self.charge_point_id)

    @on(Action.boot_notification)
    async def on_boot_notification(self, **kwargs):
        logging.info("Received a BootNotification")
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

        return call_result.Heartbeat(current_time=datetime.utcnow().isoformat())

    @on(Action.authorize)
    def on_authorize(self, **kwargs):
        logging.info("Received a Authorize")

        authorize_id_token = kwargs["id_token"]["id_token"]
        print(f"> Auth : {authorize_id_token['evseId'], authorize_id_token['connectorId'], authorize_id_token['userId']}")
        reservation_data = reservation_collection.find_one({"idToken": authorize_id_token, "reservationStatus": "ACTIVE"})
        print(f"> Auth : {reservation_data}")

        if reservation_data is None:
            logging.ERROR("Reservation not found")
            call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.no_credit))
            return call_result_authorize
        # TODO: 충전소 위치 확인, 커넥터 확인, 스타트타임 확인 -> 업데이트 해줘야함(예약시간 지남)


        match reservation_data["reservationStatus"]:
            case "ACTIVE": # "ACTIVE" -	현재 유효한 예약. 아직 예약된 시간이 아님 (예약을 생성하면 ACTIVE 상태)
                logging.info("Reservation Found")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.not_at_this_time))
            case "WAITING": # “WAITING”-	예약된 시간이 되었지만 아직 연결하지 않음(기다려주는 시간 10분이 지나지 않음)
                logging.info("reservation waiting-accepted")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.accepted))
            case "ONGOING": # "ONGOING" -	예약 시간에 도달했고, 예약자 본인이 충전 중임
                logging.info("reservation ongoing")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.concurrent_tx))
            case "EXPIRED": # "EXPIRED" -	예약 시간이 지났고, 실제 사용(충전)을 하지 않음 (노쇼)
                logging.info("reservation expired")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.expired))
            case "COMPLETED": # "COMPLETED" -	예약자가 충전을 정상적으로 수행했고, 충전이 완료됨
                logging.info("reservation completed")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.concurrent_tx))
            case "CANCELLED": # "CANCELLED" -	사용자가 직접 예약을 취소함
                logging.info("reservation cancelled")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.invalid))
            case _: # 그외 값
                logging.info("unknown error")
                call_result_authorize = call_result.Authorize(id_token_info=IdTokenInfoType(status=AuthorizationStatusEnumType.unknown))


        reservation_id = str(reservation_data["_id"])  # 예약 id
        charging_profile:Dict[str, Any] = charging_profile_collection.find_one({"reservationId": reservation_id})["chargingSchedules"]
        print(f"> Auth : {charging_profile}")

        _custom_data: Dict[str, Any] = {
            "vendorId": "ChargeSet",  # 필수 필드를 추가
            "userId": reservation_data['userId'],
            "idToken": reservation_data['idToken'],
            "chargingSchedules": charging_profile,
            "connectorId": reservation_data["connectorId"],
            "evseId": reservation_data["evseId"],
            "reservationId": reservation_id,
            "startTime": reservation_data["startTime"].strftime('%Y-%m-%d %H:%M:%S'),
            "endTime": reservation_data["endTime"].strftime('%Y-%m-%d %H:%M:%S'),
            "cost": reservation_data["cost"],
            "targetEnergyWh": reservation_data["targetEnergyWh"],
        }

        call_result_authorize.custom_data = _custom_data
        return call_result_authorize



    @on(Action.set_charging_profile)
    def on_set_charging_profile(self, **kwargs):
        return call_result.SetChargingProfile(status=GenericStatusEnumType.accepte, charging_profile_id=1, custom_data=[Dict[str, Any]])


    @on(Action.transaction_event)
    def on_transaction_event(self, **kwargs):
        # kwargs: evse_id, connector_id, user_id, id_token, reservation_id, charging_schedules, start_time, end_time
        # TODO evse값 업데이트, transaction 컬렉션에 값 업데이트
        if kwargs["event_type"] == "Started":
            logging.info("Transaction Started")
            transaction_collection.insert_one({
                "stationId": self.charge_point_id,
                "evseId": kwargs['custom_data']['evse_id'],
                "connectorId": kwargs['custom_data']['connector_id'],
                "userId": kwargs['custom_data']['user_id'],
                "idToken": kwargs['custom_data']['id_token'],
                "reservationId": ObjectId(kwargs['custom_data']['reservation_id']),
                "startTime":datetime.fromisoformat(kwargs['custom_data']['start_time']),
                "endTime":datetime.fromisoformat(kwargs['custom_data']['end_time']),
                "energyWh": kwargs['custom_data']['energyWh'],
                "cost": kwargs['custom_data']['cost'],
                "transactionStatus":"CHARGING",
                "startSchedule": datetime.now(),
                "chargingProfileSnapshots": kwargs['custom_data']['charging_schedules']
            })
            evse_collection.update_one(
                {"evseId": kwargs['custom_data']["evse_id"]}, {"$set": {"evseStatus": "CHARGING"}})
        if kwargs["event_type"] == "Ended":
            logging.info("Transaction Ended")
            transaction_collection.update_one(
                {"reservationId":ObjectId(kwargs['custom_data']["reservation_id"])},{"$set":{"transactionStatus":"COMPLETED"}})
            reservation_collection.update_one(
                {"_id":ObjectId(kwargs['custom_data']["reservation_id"])},{"$set":{"reservationStatus":"COMPLETED"}}
            )
            evse_collection.update_one(
                {"evseId": kwargs['custom_data']['evse_id']}, {"$set": {"evseStatus": "AVAILABLE"}}
            )
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
