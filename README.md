# HA-MotionBlinds_BLE

This Home Assistant integration adds support for **MotionBlinds** bluetooth motors. Beware that this integration does not work for **Eve MotionBlinds** motors.


# Setup
MotionBlinds BLE devices will be automatically discovered by Home Assistant, and shown in the *Devices & Services* part of the Home Assistant settings. Additionally, there is the option to manually add a motor by entering the MAC code. This can be done by going to the integration and clicking on "*Setup another instance of MotionBlinds BLE*".

During the setup, you will be asked what capabilities your MotionBlind has. There are 3 different capabilities:

- **Position**: for blinds that only offer the capacity to change the position. Used for regular roller blinds, curtain blinds,
- **Tilt**: for blinds that only offer the capability to tilt. Used for tilt-only venetian blinds.
- **Position & tilt**: for blinds that offer both position and tilt capabilities. Used for regular venetian blinds.

# Control


# Services
The MotionBlinds BLE integration offers four different services, in addition to the ones of a standard Home Assistant [`Cover`](https://www.home-assistant.io/integrations/cover/#services) entity, which can be used to automate your MotionBlinds:
- **Connect**: Used to connect to a motor. Optionally, one can specify how long to stay connected for. By default, this is 15 seconds.
- **Disconnect**: Used to terminate the connection with a motor, even if Home Assistant is currently connecting to it.
- **Favorite**: Used to make the blind move to the favorite position (if not connected, this command will also connect).
- **Status**: Used to retrieve blind position, tilt and battery percentage (if not connected, this command will also connect).

# Troubleshooting

## Proxy

If you are using a proxy and are facing issues discovering your MotionBlinds, try unplugging your ESPHome proxy and plugging it back in.