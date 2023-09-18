# HA-MotionBlinds_BLE

This Home Assistant integration adds support for **MotionBlinds** bluetooth motors. Beware that this integration does not work for **Eve MotionBlinds** motors. **Eve MotionBlinds** can be added to Home Assistant using the [HomeKit](https://www.home-assistant.io/integrations/homekit_controller/) integration.


# Setup
MotionBlinds BLE devices will be automatically discovered by Home Assistant, and shown in the *Devices & Services* part of the Home Assistant settings. Additionally, there is the option to manually add a motor by entering the MAC code. This can be done by going to the integration and clicking on "*Setup another instance of MotionBlinds BLE*".

During the setup, you will be asked what kind of blind your MotionBlind is. There are 8 different blind types:

- **Roller blind**: has the ability to change position and speed.
- **Honeycomb blind**: has the ability to change position and speed.
- **Roman blind**: has the ability to change position and speed.
- **Venetian blind**: has the ability to change position, tilt and speed.
- **Venetian blind (tilt-only)**: has the ability to change tilt and speed.
- **Double Roller blind**: has the ability to change position, tilt and speed.
- **Curtain blind**: has the ability to change position. May need to be calibrated if the end positions are lost, which can be done my moving the device in any direction using the buttons.
- **Vertical blind**: has the ability to change position and tilt. May need to be calibrated if the end positions are lost, which has to be done using the MotionBlinds BLE app.

# Control
Upon controlling your MotionBlind using Home Assistant, the motor will automatically first be connected to. The default time the blinds will stay connected to is 15 seconds, which is reset to 15 seconds every time you control your blinds with Home Assistant. There is also the option to connect to your blind for longer periods of time using [services](#services), though this may significantly impact battery life.

There is also the option to move the blinds to the favorite position, which can be done by clicking the *favorite* button.

# Services
The MotionBlinds BLE integration offers four different services, in addition to the ones of a standard Home Assistant [`Cover`](https://www.home-assistant.io/integrations/cover/#services) entity, which can be used to automate your MotionBlinds:
- **Connect**: Used to connect to a motor. By default, the motor will stay connected to for 15 seconds. Optionally, one can specify a different time before the connection with the motor is terminated by Home Assistant. **However**, staying connected to the motor for longer than 15 seconds may significantly reduce battery life.
- **Disconnect**: Used to terminate the connection with a motor, even if Home Assistant is currently connecting to it.
- **Favorite**: Used to make the blind move to the favorite position (if not connected, this command will also connect).
- **Status**: Used to retrieve blind position, tilt and battery percentage (if not connected, this command will also connect).

# Troubleshooting

## Proxy

If you are using a proxy and are facing issues discovering your MotionBlinds, try unplugging your ESPHome proxy and plugging it back in.