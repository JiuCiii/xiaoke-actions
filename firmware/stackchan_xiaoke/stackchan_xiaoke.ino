#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include "config.h"
#include "device_actions.h"

namespace {

constexpr unsigned long kPollIntervalMs = 1500;
constexpr unsigned long kHeartbeatIntervalMs = 30000;
constexpr unsigned long kWifiRetryMs = 5000;

WiFiClientSecure tlsClient;
unsigned long lastPollAt = 0;
unsigned long lastHeartbeatAt = 0;
unsigned long lastWifiAttemptAt = 0;
String currentAction;

String endpoint(const char* path) {
  return String(XIAOKE_ACTIONS_BASE_URL) + path;
}

void addHeaders(HTTPClient& http) {
  http.addHeader("Authorization", String("Bearer ") + STACKCHAN_DEVICE_TOKEN);
  http.addHeader("X-Stackchan-Device", STACKCHAN_DEVICE_ID);
  http.addHeader("Accept", "application/json");
}

bool postJson(const char* path, JsonDocument& body, JsonDocument& response) {
  HTTPClient http;
  if (!http.begin(tlsClient, endpoint(path))) {
    return false;
  }
  addHeaders(http);
  http.addHeader("Content-Type", "application/json");

  String serialized;
  serializeJson(body, serialized);
  int status = http.POST(serialized);
  String payload = http.getString();
  http.end();
  if (status < 200 || status >= 300) {
    Serial.printf("[stackchan] POST %s failed: %d %s\n", path, status, payload.c_str());
    return false;
  }
  return deserializeJson(response, payload) == DeserializationError::Ok;
}

void sendHeartbeat() {
  JsonDocument body;
  body["device_id"] = STACKCHAN_DEVICE_ID;
  body["firmware_version"] = "xiaoke-stackchan-0.1";
  body["rssi"] = WiFi.RSSI();
  body["free_heap"] = ESP.getFreeHeap();
  body["current_action"] = currentAction.length() ? currentAction : nullptr;
  JsonDocument response;
  postJson("/stackchan/heartbeat", body, response);
}

void reportResult(const String& id, bool ok, const String& error) {
  JsonDocument body;
  body["id"] = id;
  body["ok"] = ok;
  if (ok) {
    body["result"]["firmware"] = "xiaoke-stackchan-0.1";
  } else {
    body["error"] = error;
  }
  JsonDocument response;
  postJson("/stackchan/result", body, response);
}

bool executeCommand(JsonObject command, String& error) {
  const String action = command["action"] | "";
  JsonObject payload = command["payload"].as<JsonObject>();
  currentAction = action;

  if (action == "speak") {
    return xiaoke::speak(payload["text"] | "", error);
  }
  if (action == "emote") {
    return xiaoke::emote(payload["expression"] | "", error);
  }
  if (action == "move_head") {
    return xiaoke::moveHead(payload["pitch"] | 0.0, payload["yaw"] | 0.0, error);
  }
  if (action == "wiggle") {
    return xiaoke::wiggle(error);
  }
  error = "unknown_action";
  return false;
}

void pollOnce() {
  HTTPClient http;
  if (!http.begin(tlsClient, endpoint("/stackchan/poll"))) {
    return;
  }
  addHeaders(http);
  int status = http.GET();
  String payload = http.getString();
  http.end();
  if (status != 200) {
    Serial.printf("[stackchan] poll failed: %d %s\n", status, payload.c_str());
    return;
  }

  JsonDocument response;
  if (deserializeJson(response, payload) != DeserializationError::Ok) {
    Serial.println("[stackchan] invalid poll JSON");
    return;
  }
  JsonObject command = response["command"].as<JsonObject>();
  if (command.isNull()) {
    return;
  }

  String error;
  const String id = command["id"] | "";
  bool ok = executeCommand(command, error);
  currentAction = "";
  reportResult(id, ok, error);
}

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  unsigned long now = millis();
  if (now - lastWifiAttemptAt < kWifiRetryMs) {
    return;
  }
  lastWifiAttemptAt = now;
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  xiaoke::beginDevice();
  tlsClient.setCACert(STACKCHAN_ROOT_CA);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void loop() {
  ensureWifi();
  if (WiFi.status() != WL_CONNECTED) {
    delay(50);
    return;
  }

  unsigned long now = millis();
  if (now - lastHeartbeatAt >= kHeartbeatIntervalMs) {
    lastHeartbeatAt = now;
    sendHeartbeat();
  }
  if (now - lastPollAt >= kPollIntervalMs) {
    lastPollAt = now;
    pollOnce();
  }
  delay(10);
}
