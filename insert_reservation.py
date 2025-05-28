import os
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from dotenv import load_dotenv
from datetime import datetime, timedelta


load_dotenv()

mongodb_uri = os.getenv("MONGODB_URI")
client = MongoClient(mongodb_uri)

db = client["charge-set"]
reservation_collection = db["reservation"]
charging_profile_collection = db["chargingProfile"]

now = datetime.now()
end = now + timedelta(minutes=3)

doc1 = {
    "stationId": "ST-001",
    "evseId": "EVSE-ST1-001",
    "connectorId": 1,
    "userId": "682d6f8a3792904b5c987afe",
    "idToken": "token-6789",
    "startTime": now,
    "endTime": end,
    "targetEnergyWh": 1200,
    "cost": 420,
    "reservationStatus": "ACTIVE",
    "createdAt": now
}
result = reservation_collection.insert_one(doc1)
print("Inserted reservation_collection ID:", result.inserted_id)

doc2 = {

  "reservationId": str(result.inserted_id),
  "chargingProfileKind": "ABSOLUTE",
  "startSchedule": now,
  "chargingSchedules": [
    {
      "startPeriod": 0,
      "limit": 6000,
      "useESS": False
    },
    {
      "startPeriod": 120,
      "limit": 60000,
      "useESS": True
    },
    {
      "startPeriod": 180,
      "limit": 0,
      "useESS": False
    },

  ]
}

result = charging_profile_collection.insert_one(doc2)
print("Inserted charging_profile_collection ID:", result.inserted_id)