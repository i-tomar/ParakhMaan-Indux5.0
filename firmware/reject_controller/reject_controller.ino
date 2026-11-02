// ParakhMaan reject controller for Arduino Uno/Nano or ESP32. NOT yet tested on physical hardware.
//
// Serial protocol at 115200 baud, matching backend/app/services/line/actuator.py:
//   Host:       R,<unit_code>,<delay_ms>\n
//   Controller: A,<unit_code>\n        (acknowledged immediately)
// After <delay_ms> the diverter output pulses for PULSE_MS. Queued rejects never block each other.

const uint8_t DIVERTER_PIN = 9;
const unsigned long PULSE_MS = 80;
const uint8_t QUEUE = 16;

struct Job { unsigned long fireAt; bool used; };
Job jobs[QUEUE];
unsigned long pulseEnd = 0;
String line;

void setup() {
  pinMode(DIVERTER_PIN, OUTPUT);
  digitalWrite(DIVERTER_PIN, LOW);
  Serial.begin(115200);
  line.reserve(64);
}

void handle(const String &message) {
  int first = message.indexOf(',');
  int second = message.lastIndexOf(',');
  if (message.charAt(0) != 'R' || first < 0 || second <= first) return;
  String unit = message.substring(first + 1, second);
  unsigned long delayMs = message.substring(second + 1).toInt();
  for (uint8_t i = 0; i < QUEUE; i++) {
    if (!jobs[i].used) {
      jobs[i].used = true;
      jobs[i].fireAt = millis() + delayMs;
      Serial.print("A,");
      Serial.println(unit);
      return;
    }
  }
  // Queue full: no acknowledgement, so the backend records NO_ACK.
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      handle(line);
      line = "";
    } else if (line.length() < 60) {
      line += c;
    }
  }
  unsigned long now = millis();
  for (uint8_t i = 0; i < QUEUE; i++) {
    if (jobs[i].used && (long)(now - jobs[i].fireAt) >= 0) {
      jobs[i].used = false;
      digitalWrite(DIVERTER_PIN, HIGH);
      pulseEnd = now + PULSE_MS;
    }
  }
  if (pulseEnd && (long)(now - pulseEnd) >= 0) {
    digitalWrite(DIVERTER_PIN, LOW);
    pulseEnd = 0;
  }
}
