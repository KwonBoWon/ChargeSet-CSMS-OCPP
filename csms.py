# SPDX-License-Identifier: Apache-2.0
# Copyright 2020 - 2024 Pionix GmbH and Contributors to EVerest
import asyncio
import logging
from warnings import catch_warnings

from central_system import ChargePointHandler
import http
import websockets_test
import ssl
from pathlib import Path
import argparse
from pymongo import MongoClient




__version__ = "0.1.0"

reject_auth = False
"""
{
  "_id": {
    "$oid": "67fb7450fcb584c29e147773"
  },
  "stationId": "ST-001",
  "evseId": "EVSE-ST1-001",
  "connectorId": 1,
  "idToken": "token-3456",
  "startTime": {
    "$date": "2025-04-14T13:00:00.000Z"
  },
  "endTime": {
    "$date": "2025-04-14T20:00:00.000Z"
  },
  "targetEnergyWh": 15000,
  "reservationStatus": "ACTIVE",
  "createdAt": {
    "$date": "2025-04-12T09:00:00.000Z"
  },
  "userId": "67dfc4c4dbbe444d632a2421"
}
"""


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
        except websockets_test.exceptions.ConnectionClosedOK:
            logging.info("Client closed the connection normally (code 1000).")


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

    server = await websockets_test.serve(
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
