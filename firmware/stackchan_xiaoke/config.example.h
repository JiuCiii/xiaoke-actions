#pragma once

#define WIFI_SSID "replace-with-wifi-name"
#define WIFI_PASSWORD "replace-with-wifi-password"

#define XIAOKE_ACTIONS_BASE_URL "https://xiaoke-actions.onrender.com"
#define STACKCHAN_DEVICE_TOKEN "replace-with-the-render-device-token"
#define STACKCHAN_DEVICE_ID "stackchan-01"

// Supply the root CA that validates the Render certificate chain.
// Do not use setInsecure() with a bearer token.
static const char STACKCHAN_ROOT_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
replace-with-root-ca
-----END CERTIFICATE-----
)EOF";
