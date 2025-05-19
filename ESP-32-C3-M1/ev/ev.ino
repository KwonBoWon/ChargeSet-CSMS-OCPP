void setup() {
  Serial.begin(115200);
  delay(1000);
  // ID 토큰 전송
  Serial.println("token-3456");
}

void loop() {
  if (Serial.available()) {
    String json = Serial.readStringUntil('\n');
    json.trim();
    Serial.println("Response JSON:");
    Serial.println(json);
    // TODO 여기서 스케줄대로 LED 해야함
  }
}


// token-3456