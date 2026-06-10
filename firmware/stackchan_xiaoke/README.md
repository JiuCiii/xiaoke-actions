# Xiaoke Stack-chan Firmware Scaffold

This scaffold implements the network contract without guessing the installed
Stack-chan face, servo, or speech libraries.

## Ready

- Wi-Fi reconnect
- HTTPS with CA validation
- bearer-token device authentication
- heartbeat
- command polling
- result reporting
- dispatch for `speak`, `emote`, `move_head`, and `wiggle`

## Hardware adapters still required

Implement these functions in `device_actions.cpp` using the firmware and
hardware actually installed on the CoreS3:

- `speak`
- `emote`
- `moveHead`
- `wiggle`

Copy `config.example.h` to `config.h` locally. Keep `config.h` out of Git
because it contains Wi-Fi credentials and the device token.
