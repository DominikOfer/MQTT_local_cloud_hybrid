# Based on https://github.com/aws/aws-iot-device-sdk-python-v2/tree/main/samples
# Adapted to fit the use case of a lightbulb mqtt sensor
import json

from awscrt import mqtt
from awsiot import iotshadow
import sys
import traceback
from uuid import uuid4
import time
import logging

# Parse arguments
import command_line_utils

cmdUtils = command_line_utils.CommandLineUtils("Shadow - Keep a property in sync between device and server.")
cmdUtils.add_common_mqtt_commands()
cmdUtils.add_common_proxy_commands()
cmdUtils.add_common_logging_commands()
cmdUtils.register_command("key", "<path>", "Path to your key in PEM format.", True, str)
cmdUtils.register_command("cert", "<path>", "Path to your client certificate in PEM format.", True, str)
cmdUtils.register_command("port", "<int>", "Connection port. AWS IoT supports 433 and 8883 (optional, default=auto).",
                          type=int)
cmdUtils.register_command("client_id", "<str>", "Client ID to use for MQTT connection (optional, default='Lightbulb01').",
                          default="Lightbulb01") # + str(uuid4()))
cmdUtils.register_command("thing_name", "<str>", "The name assigned to your IoT Thing", required=True)
cmdUtils.register_command("interval", "<str>",
                          "Interval for publishing state (optional, default=10').",
                          default=10)
cmdUtils.register_command("shadow_property_one", "<str>", "The name of the first shadow property you want to observe (optional, default='state')", default="state")

# Needs to be called so the command utils parse the commands
cmdUtils.get_args()

# Using globals to simplify code
mqtt_connection = None
state_topic = "light/" + cmdUtils.get_command("client_id")
control_topic = "light/" + cmdUtils.get_command("client_id") + "/control"
states = ["ON", "OFF"]
interval = cmdUtils.get_command("interval")
shadow_thing_name = cmdUtils.get_command("thing_name")
shadow_property_one = cmdUtils.get_command("shadow_property_one")


class Lightbulb:
    def __init__(self):
        self.state = ""
        self.state_old = ""
        self.last_pub_time = time.time()
        self.request_tokens = set()


lightbulb = Lightbulb()

############################# Callbacks ######################################
# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))


def on_update_shadow_accepted(response):
    logging.debug("Update shadow accepted")

    try:
        lightbulb.request_tokens.remove(response.client_token)
    except KeyError:
        print("Ignoring on_update_shadow_accepted message due to unexpected token.")
        return

    try:
        if response.state.reported != None:
            if shadow_property_one in response.state.reported:
                print("Finished updating reported shadow value to '{}'.".format(response.state.reported[shadow_property_one]))
            else:
                print ("Could not find shadow property with name: '{}'.".format(shadow_property_one)) # type: ignore
        else:
            print("Shadow states cleared.")
    except:
        exit("Updated shadow misses target property")

def on_update_shadow_rejected(error):
    logging.error("Update shadow rejected")
    try:
        lightbulb.request_tokens.remove(error.client_token)
    except KeyError:
        print("Ignoring on_update_shadow_rejected message due to unexpected token.")
        return

    exit("Update shadow request was rejected. code:{} message:'{}'".format(
        error.code, error.message))

def on_get_shadow_accepted(response):  # Response is an iotshadow.GetShadowResponse Type
    logging.debug("Get shadow accepted")

    try:
        # Remove the client token from the request_tokens
        lightbulb.request_tokens.remove(response.client_token)
    except KeyError:
        logging.error("Ignoring get_shadow_accepted due to unexpected token")
        return

    logging.debug(response.state)
    if response.state:
        if response.state.delta:
            value = response.state.delta.get(shadow_property_one)
            if value:
                logging.debug("Shadow contains delta value {}".format(value))
                change_shadow_value(value, False)
            return

        if response.state.reported:
            value = response.state.reported.get(shadow_property_one)
            if value:
                logging.debug("Shadow contains reported value {}".format(value))
                change_shadow_value(value, False)


def on_get_shadow_rejected(error):
    logging.error("Get shadow rejected")

    try:
        lightbulb.request_tokens.remove(error.client_token)
    except KeyError:
        print("Ignoring get_shadow_rejected message due to unexpected token.")
        return

    exit("Get request was rejected. code:{} message:'{}'".format(
        error.code, error.message))


def on_shadow_delta_updated(delta):
    logging.debug("Shadow delta updated")
    logging.debug(delta)
    if delta.state and (shadow_property_one in delta.state):
        value = delta.state[shadow_property_one]
        if value:
            logging.debug("Delta reports that desired value is {}".format(value))
            change_shadow_value(value, False)
    else:
        print("  Delta did not report a change in '{}'".format(shadow_property_one))

def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    logging.debug("Received message from topic '{}': {}".format(topic, payload))
    message_handler(topic, payload)

def on_publish_update_shadow(future):
    try:
        future.result()
        logging.debug("Update request published.")
    except Exception as e:
        logging.error("Failed to publish update request.")
        exit(e)

##################Handling Functions##################################
def message_handler(topic, payload):
    if topic == control_topic:
        logging.debug("control message received on {}".format(topic))
        try:
            json_payload = json.loads(payload.decode("utf-8"))
            update_state(json_payload["state"])
        except KeyError as e:
            logging.error("KeyError in MessageHandler: " + str(e))


def publish_state():
    pubflag = False
    if time.time() - lightbulb.last_pub_time >= interval:
        pubflag = True
    if lightbulb.state != lightbulb.state_old or pubflag:
        print("Publishing state to topic '{}': {}".format(state_topic, lightbulb.state))
        mqtt_connection.publish(
            topic=state_topic,
            payload=json.dumps("{'state': \'" + lightbulb.state + "\'}"),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            retain=True)
        logging.debug(
            "updating lightbulb state_old from: {} to: {}".format(lightbulb.state_old, lightbulb.state))
        lightbulb.state_old = lightbulb.state
        lightbulb.last_pub_time = time.time()


def update_state(state):
    state = state.upper()
    if state == states[0] or state == states[1]:  # Valid state
        logging.debug("updating lightbulb state from: {} to: {}".format(lightbulb.state, state))
        lightbulb.state = state
        logging.debug("updating shadow because of control topic")
        change_shadow_value(state, True)
    else:
        logging.info("Received invalid state: {}".format(state))

def change_shadow_value(value, desired):
    logging.debug("Changing lightbulb state to {}".format(value))
    lightbulb.state = value

    logging.debug("Updating reported shadow ")
    token = str(uuid4())
    if not desired:
        request = iotshadow.UpdateShadowRequest(
            thing_name=shadow_thing_name,
            state=iotshadow.ShadowState(
                reported={shadow_property_one: lightbulb.state}
            ),
            client_token=token,
        )
    else:
        request = iotshadow.UpdateShadowRequest(
            thing_name=shadow_thing_name,
            state=iotshadow.ShadowState(
                reported={shadow_property_one: lightbulb.state},
                desired={shadow_property_one: lightbulb.state}
            ),
            client_token=token,
        )
    future = shadow_client.publish_update_shadow(request, mqtt.QoS.AT_LEAST_ONCE)
    lightbulb.request_tokens.add(token)
    future.add_done_callback(on_publish_update_shadow)

# Function for gracefully quitting
def exit(msg_or_exception):
    if isinstance(msg_or_exception, Exception):
        print("Exiting due to exception.")
        traceback.print_exception(msg_or_exception.__class__, msg_or_exception, sys.exc_info()[2])
    else:
        print("Exiting:", msg_or_exception)

    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    logging.info("Disconnected!")


if __name__ == '__main__':
    print("starting")
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

    mqtt_connection = cmdUtils.build_direct_mqtt_connection(on_connection_interrupted, on_connection_resumed)
    logging.info("Connecting to {} with client ID '{}'...".format(
        cmdUtils.get_command(cmdUtils.m_cmd_endpoint), cmdUtils.get_command("client_id")))
    connect_future = mqtt_connection.connect()

    # Create IoT Shadow Client for this connection
    shadow_client = iotshadow.IotShadowClient(mqtt_connection)

    connect_future.result()
    logging.info("Connected!")

    try:
        # Subscribe to shadow topics
        logging.info("Subscribing to Update responses...")
        update_accepted_subscribed_future, _ = shadow_client.subscribe_to_update_shadow_accepted(
            request=iotshadow.UpdateShadowSubscriptionRequest(thing_name=shadow_thing_name), qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_update_shadow_accepted)

        update_rejected_subscribed_future, _ = shadow_client.subscribe_to_update_shadow_rejected(
            request=iotshadow.UpdateShadowSubscriptionRequest(thing_name=shadow_thing_name), qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_update_shadow_rejected)

        # Wait for subscription results
        subscribe_result = update_accepted_subscribed_future.result()
        logging.info("Subscribed with {}".format(str(subscribe_result)))

        subscribe_result = update_rejected_subscribed_future.result()
        logging.info("Subscribed with {}".format(str(subscribe_result)))

        logging.info("Subscribing to Get responses...")
        get_accepted_subscribed_future, _ = shadow_client.subscribe_to_get_shadow_accepted(
            request=iotshadow.GetShadowSubscriptionRequest(thing_name=shadow_thing_name),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_get_shadow_accepted)

        get_rejected_subscribed_future, _ = shadow_client.subscribe_to_get_shadow_rejected(
            request=iotshadow.GetShadowSubscriptionRequest(thing_name=shadow_thing_name),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_get_shadow_rejected)

        # Wait for subscription results
        subscribe_result = update_accepted_subscribed_future.result()
        logging.info("Subscribed with {}".format(str(subscribe_result)))

        subscribe_result = update_rejected_subscribed_future.result()
        logging.info("Subscribed with {}".format(str(subscribe_result)))

        logging.info("Subscribing to Delta events...")
        delta_subscribed_future, _ = shadow_client.subscribe_to_shadow_delta_updated_events(
            request=iotshadow.ShadowDeltaUpdatedSubscriptionRequest(thing_name=shadow_thing_name),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_shadow_delta_updated)

        # Wait for subscription results
        subscribe_result = delta_subscribed_future.result()
        logging.info("Subscribed with {}".format(str(subscribe_result)))

        # Subscribe to control topic
        logging.info("Subscribing to topic '{}'...".format(control_topic))
        subscribe_future, packet_id = mqtt_connection.subscribe(
            topic=control_topic,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_message_received)

        subscribe_result = subscribe_future.result()
        logging.info("Subscribed with {}".format(str(subscribe_result['qos'])))

        # Publish a message to /get to trigger a publish of the current shadow
        # Using a token to be able to trace response
        logging.debug("Requesting current shadow")

        token = str(uuid4())
        publish_get_future = shadow_client.publish_get_shadow(
            request=iotshadow.GetShadowRequest(thing_name=shadow_thing_name, client_token=token),
            qos=mqtt.QoS.AT_LEAST_ONCE)

        lightbulb.request_tokens.add(token)

        while 1 == 1:
            publish_state()
            time.sleep(1)

    except KeyboardInterrupt:
        exit("Keyboard Interrupt")
    except Exception as e:
        exit(e)
