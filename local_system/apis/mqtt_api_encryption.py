#!/usr/bin/env python
# encoding: utf-8
import json
import paho.mqtt.publish as publish
import paho.mqtt.subscribe as subscribe

from flask import Flask, jsonify, render_template, request, make_response
from paho.mqtt import MQTTException
from helper import aes_encryption
import ast

app = Flask(__name__)
broker = '10.0.0.100'
padding_character = '{'


# Helpers
def custom_message(message, status_code):
    return make_response(jsonify(message), status_code)


def get_key_for_sensor(sensor):
    try:
        text_file = open("./helper/encryption_secrets.txt", "r")
        contents = text_file.read()
        secrets_dict = ast.literal_eval(contents)
        text_file.close()
        return secrets_dict[sensor]
    except Exception as e:
        print(e)
        return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status/', methods=['GET'])
def query_status():
    sensor = request.args.get('sensor')
    topic = request.args.get('topic')
    if type(sensor) == str and type(topic) == str:
        key = get_key_for_sensor(sensor)
        if key is not None:
            try:
                msg = subscribe.simple(topic + '/' + sensor, qos=1, hostname=broker, client_id="mqtt_api")
                print("payload: " + msg.payload.decode("utf-8"))
                decrypted_payload = aes_encryption.decrypt_message(msg.payload, key, padding_character)
                print("decrypted: " + decrypted_payload)
                return jsonify({'topic': msg.topic, 'payload': decrypted_payload})
            except MQTTException as e:
                if "not authorised" in e.args[0]:
                    return custom_message({'message': 'Not authorized'}, 401)
                else:
                    return custom_message({'message': 'Something went wrong'}, 500)
        else:
            return custom_message({'message': 'Decryption error for: ' + sensor}, 400)
    else:
        return custom_message({'message': 'Sensor and topic are required'}, 400)


@app.route('/api/control', methods=['POST'])
def control_sensor():
    try:
        record = json.loads(request.data)
        if 'sensor' in record and 'topic' in record and 'message' in record:
            key = get_key_for_sensor(record['sensor'])
            if key is not None:
                encrypted_payload = aes_encryption.encrypt_message(record['message'], key, padding_character)
                print("enc: " + encrypted_payload.decode("utf-8"))
                decrypted_payload = aes_encryption.decrypt_message(encrypted_payload, key, padding_character)
                print("dec: " + decrypted_payload)
                publish.single(record['topic'] + '/' + record['sensor'] + '/' + 'control', encrypted_payload,
                               hostname=broker, client_id="mqtt_api", retain=True)
                return jsonify(record)
            else:
                return custom_message({'message': 'Encryption error for sensor: ' + record['sensor']}, 400)
        else:
            return custom_message({'message': 'Sensor, topic and message are required'}, 400)
    except ValueError as e:
        print(e)
        return custom_message({'message': 'Invalid JSON'}, 400)
    except MQTTException as e:
        if "not authorised" in e.args[0]:
            return custom_message({'message': 'Not authorized'}, 401)
        else:
            return custom_message({'message': 'Something went wrong'}, 500)


# True for easy debugging with pycharm
app.run(host='0.0.0.0', debug=False)
