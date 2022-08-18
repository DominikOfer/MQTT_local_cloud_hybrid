# Based on https://github.com/aws/aws-iot-device-sdk-python-v2/tree/main/samples
# Adapted to fit the use case of a lightbulb mqtt sensor

from uuid import uuid4
from awscrt import mqtt
import time
import json
import logging

# Parse arguments
import command_line_utils

cmdUtils = command_line_utils.CommandLineUtils("Sensor Simulator.")
cmdUtils.add_common_mqtt_commands()
cmdUtils.add_common_proxy_commands()
cmdUtils.add_common_logging_commands()
cmdUtils.register_command("key", "<path>", "Path to your key in PEM format.", True, str)
cmdUtils.register_command("cert", "<path>", "Path to your client certificate in PEM format.", True, str)
cmdUtils.register_command("port", "<int>",
                          "Connection port for direct connection. " +
                          "AWS IoT supports 433 and 8883 (optional, default=8883).",
                          False, int)
cmdUtils.register_command("client_id", "<str>",
                          "Client ID to use for MQTT connection (optional, default='Lightbulb01').",
                          default="Lightbulb01")  # + str(uuid4()))
cmdUtils.register_command("interval", "<str>",
                          "Interval for publishing status (optional, default=10').",
                          default=10)
# Needs to be called so the command utils parse the commands
cmdUtils.get_args()

# Using globals to simplify code
mqtt_connection = None
message_topics = ["light/Lightbulb01", "light/Lightbulb01/control"]
status_topic = "light/" + cmdUtils.get_command("client_id")
control_topic = "light/" + cmdUtils.get_command("client_id") + "/control"
states = ["ON", "OFF"]
interval = cmdUtils.get_command("interval")

lightbulb = {
    "state": "",
    "state_old": "",
    "last_pub_time": time.time()
}


# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))


# Callback when the subscribed topic receives a message
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    print("Received message from topic '{}': {}".format(topic, payload))
    message_handler(topic, payload)


def message_handler(topic, payload):
    if topic == control_topic:
        logging.debug("control message received")
        try:
            json_payload = json.loads(payload.decode("utf-8"))
            update_status(json_payload["status"])
        except KeyError as e:
            logging.error("KeyError in MessageHandler: " + str(e))


def publish_status():
    pubflag = False
    if time.time()-lightbulb["last_pub_time"] >= interval:
        pubflag=True
    if lightbulb["state"] != lightbulb["state_old"] or pubflag:
        print("Publishing status to topic '{}': {}".format(status_topic, lightbulb["state"]))
        mqtt_connection.publish(
            topic=status_topic,
            payload=json.dumps("{'status': " + lightbulb["state"] + "}"),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            retain=True)
        logging.debug("updating lightbulb status_old from: {} to: {}".format(lightbulb["state_old"], lightbulb["state"]))
        lightbulb["state_old"] = lightbulb["state"]
        lightbulb["last_pub_time"] = time.time()

def update_status(status):
    status = status.upper()
    if status == states[0] or status == states[1]:  # Valid status
        logging.debug("updating lightbulb status from: {} to: {}".format(lightbulb["state"], status))
        lightbulb["state"] = status
    else:
        logging.info("Received invalid state: {}".format(status))


if __name__ == '__main__':
    print("starting")
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
    logging.info("Publishing on " + status_topic)
    logging.info("send control to " + control_topic)
    logging.info("Sensors States are " + "/".join(states))

    # Create a connection using a certificate and key.
    # Note: The data for the connection is gotten from cmdUtils.
    # (see build_direct_mqtt_connection for implementation)
    mqtt_connection = cmdUtils.build_direct_mqtt_connection(on_connection_interrupted, on_connection_resumed)

    logging.info("Connecting to {} with client ID '{}'...".format(
        cmdUtils.get_command(cmdUtils.m_cmd_endpoint), cmdUtils.get_command("client_id")))

    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    logging.info("Connected!")

    # Subscribe to control topic
    logging.info("Subscribing to topic '{}'...".format(control_topic))
    subscribe_future, packet_id = mqtt_connection.subscribe(
        topic=control_topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received)

    subscribe_result = subscribe_future.result()
    logging.info("Subscribed with {}".format(str(subscribe_result['qos'])))

    try:
        while (1 == 1):
            publish_status()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Interrupted by keyboard")
        # Disconnect
        logging.info("Disconnecting...")
        disconnect_future = mqtt_connection.disconnect()
        disconnect_future.result()
        logging.info("Disconnected!")
