#include "M5StickCPlus2.h"
#include "ArduinoJson.h"

struct ChargingSchedule {
  int startPeriod;
  int limit;
  bool useESS;
};

ChargingSchedule schedules[10];  // 최대 10개 스케줄
int scheduleCount = 0;
unsigned long startTime;

void setup() {
  M5.begin();
  Serial.begin(115200);
  delay(1000);

  M5.Lcd.setRotation(3);
  M5.Lcd.fillScreen(WHITE);
  M5.Lcd.setTextColor(BLACK);
  M5.Lcd.setTextSize(4);

  M5.Lcd.setCursor(30, 50);
  M5.Lcd.printf("Waiting");
  
  Serial.println("token-6789");

  startTime = millis();
}

void displaySchedule(ChargingSchedule s) {  

  if(s.limit<=30000){
    M5.Lcd.fillScreen(GREEN);
    M5.Lcd.setTextColor(BLACK);
    M5.Lcd.setCursor(0, 10);
    M5.Lcd.printf(" Standard\n Charging\n %dW", s.limit);
  }
  else{
    M5.Lcd.fillScreen(BLUE);
    M5.Lcd.setTextColor(BLACK);
    M5.Lcd.setCursor(0, 10);
    M5.Lcd.printf(" Fast\n Charging\n %dW", s.limit);
  }
}
// 30000: 완속, 60000: 고속
// 충전 대기중/충전 시작/완속 충전중입니다/고속충전중입니다/충전이 끝났습니다.
void parseScheduleJson(String json) {
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, json);
  if (err) {
    //Serial.println(err.c_str());
    return;
  }

  JsonArray arr = doc["chargingSchedules"];
  scheduleCount = 0;
  for (JsonObject obj : arr) {
    if (scheduleCount >= 10) break;
    schedules[scheduleCount].startPeriod = obj["start_period"];
    schedules[scheduleCount].limit = obj["limit"];
    schedules[scheduleCount].useESS = obj["use_eSS"];
    scheduleCount++;
  }
}

void loop() {
  if (Serial.available()) {
    String json = Serial.readStringUntil('\n');
    json.trim();
    parseScheduleJson(json);
    startTime = millis();  // 타이머 초기화
  }

  // 현재 경과 시간(초 단위)
  unsigned long elapsed = (millis() - startTime) / 1000;
  ChargingSchedule* current = nullptr;

  for (int i = 0; i < scheduleCount; i++) {
    if (elapsed >= schedules[i].startPeriod) {
      current = &schedules[i];
    }
  }

  static int lastShownLimit = -1;
  if (current) {
    if (current->limit == 0 && lastShownLimit != 0) {
      M5.Lcd.fillScreen(WHITE);
      M5.Lcd.setTextColor(BLACK);
      M5.Lcd.setCursor(0, 30);
      M5.Lcd.println(" Charging\n Finished");
      lastShownLimit = 0;
    } else if (current->limit > 0 && current->limit != lastShownLimit) {
      displaySchedule(*current);
      lastShownLimit = current->limit;
    }
  }
  delay(1000);  // 1초 간격 체크
}
