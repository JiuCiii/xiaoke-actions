#pragma once

#include <Arduino.h>

namespace xiaoke {

bool beginDevice();
bool speak(const String& text, String& error);
bool emote(const String& expression, String& error);
bool moveHead(float pitch, float yaw, String& error);
bool wiggle(String& error);

}  // namespace xiaoke
