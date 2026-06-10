#include "device_actions.h"

namespace xiaoke {

bool beginDevice() {
  // Initialize M5Unified, the face renderer, servos, and audio here.
  return true;
}

bool speak(const String& text, String& error) {
  Serial.printf("[stackchan] speak: %s\n", text.c_str());
  error = "speech_adapter_not_connected";
  return false;
}

bool emote(const String& expression, String& error) {
  Serial.printf("[stackchan] emote: %s\n", expression.c_str());
  error = "face_adapter_not_connected";
  return false;
}

bool moveHead(float pitch, float yaw, String& error) {
  Serial.printf("[stackchan] move_head: pitch=%.2f yaw=%.2f\n", pitch, yaw);
  error = "servo_adapter_not_connected";
  return false;
}

bool wiggle(String& error) {
  Serial.println("[stackchan] wiggle");
  error = "servo_adapter_not_connected";
  return false;
}

}  // namespace xiaoke
