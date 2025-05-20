# SPDX-License-Identifier: Apache-2.0
# Copyright 2020 - 2024 Pionix GmbH and Contributors to EVerest
import asyncio
import logging
from warnings import catch_warnings

from central_system import ChargePointHandler
import http
import websockets
import ssl
from pathlib import Path
import argparse
from pymongo import MongoClient
import serial
import serial_asyncio
import time
import asyncio
import serial_asyncio
import serial.tools.list_ports
import json
import platform



__version__ = "0.1.0"

reject_auth = False
candidates = [] # 현재 usb 포트

async def process_request(connection, request):
    logging.info(f'request:\n{request}')
    if reject_auth:
        logging.info(
            'Rejecting authorization because of the --reject-auth command line parameter')
        return (
            http.HTTPStatus.UNAUTHORIZED,
            [],
            b'Invalid credentials\n',
        )
    return None


async def on_connect(websocket, path):
    try:
        requested_protocols = websocket.request_headers["Sec-WebSocket-Protocol"]
    except KeyError:
        logging.error(
            "Client hasn't requested any Subprotocol. Closing Connection")
        return await websocket.close()
    if websocket.subprotocol:
        logging.info("Protocols Matched: %s", websocket.subprotocol)
    else:
        logging.warning(
            "Protocols Mismatched | Expected Subprotocols: %s,"
            " but client supports  %s | Closing connection",
            websocket.available_subprotocols,
            requested_protocols,
        )
        return await websocket.close()

    if (websocket.subprotocol != "ocpp2.0.1"):
        logging.warning(
            "Unsupported subprotocol. Expected: ocpp2.0.1, but got: %s",
            requested_protocols,
        )
        return await websocket.close()
    else:
        charge_point_id = path.strip("/")
        cp = ChargePointHandler(charge_point_id, websocket)
        logging.info(f"{charge_point_id} connected using OCPP2.0.1")
        try:
            await cp.start()
        except websockets.exceptions.ConnectionClosedOK:
            logging.info("Client closed the connection normally (code 1000).")
            # 연결 종료될때
            await cp.close_connection()

class ESP32Protocol(asyncio.Protocol):
    def __init__(self, port):
        self.buffer = ""
        self.port = port

    def connection_made(self, transport):
        self.transport = transport
        print(f"ESP{self.port.device} 연결됨")

    def data_received(self, data):
        self.buffer += data.decode()
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            line = line.strip()
            print(f"수신된 ID Token: {line}")
            #self.handle_id_token(line)

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
    parser = argparse.ArgumentParser(
        description='2.0.1 CSMS')
    parser.add_argument('--version', action='version',
                        version=f'%(prog)s {__version__}')

    parser.add_argument('--host', type=str, default="0.0.0.0",
                        help='Host to listen on (default: 0.0.0.0)')

    parser.add_argument('--port', type=int, default=9000,
                        help='Plaintext port to listen on (default: 9000)')

    parser.add_argument('--reject-auth', action='store_true', default=False,
                        help='Reply with 403 error in connection')

    args = parser.parse_args()
    host = args.host
    port = args.port
    global reject_auth
    reject_auth = args.reject_auth

    server = await websockets.serve(
        on_connect, host, port, subprotocols=["ocpp2.0.1"], process_request=process_request
    )

    logging.info("OCPP CSMS Started listening to new connections...")
    await server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("CSMS stopped by user.")
        exit(0)
