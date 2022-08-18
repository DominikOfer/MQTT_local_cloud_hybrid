#!/usr/bin/env python
# encoding: utf-8
import json
import paho.mqtt.publish as publish
import paho.mqtt.subscribe as subscribe
import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template, request, make_response
from paho.mqtt import MQTTException
import ssl

app = Flask(__name__)
broker = 'rasperrypi'
certs_location = '/home/pi/Documents/scripts/certs/'

tls = dict(
    ca_certs=certs_location + 'ca.crt',
    certfile=certs_location + 'client.crt',
    keyfile=certs_location + 'client.key',
    cert_reqs=ssl.CERT_REQUIRED)


# Helpers
def custom_message(message, status_code):
    return make_response(jsonify(message), status_code)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status/', methods=['GET'])
def query_status():
    sensor = request.args.get('sensor')
    topic = request.args.get('topic')
    if type(sensor) == str and type(topic) == str:
        try:

            msg = subscribe.simple(topic + '/' + sensor, qos=1, hostname=broker, port=8883, tls=tls, client_id="mqtt_api")
            return jsonify({'topic': msg.topic, 'payload': msg.payload})
        except MQTTException as e:
            if "not authorised" in e.args[0]:
                return custom_message({'message': 'Not authorized'}, 401)
            else:
                return custom_message({'message': 'Something went wrong'}, 500)
    else:
        return custom_message({'message': 'Sensor and topic are required'}, 400)


@app.route('/api/control', methods=['POST'])
def control_sensor():
    try:
        record = json.loads(request.data)
        if 'sensor' in record and 'topic' in record and 'message' in record:
            publish.single(record['topic'] + '/' + record['sensor'] + '/' + 'control', record['message'],
                           hostname=broker, port=8883, tls=tls, client_id="mqtt_api")
            return jsonify(record)
        else:
            return custom_message({'message': 'Sensor, topic and message are required'}, 400)
    except ValueError as e:
        return custom_message({'message': 'Invalid JSON'}, 400)
    except MQTTException as e:
        if "not authorised" in e.args[0]:
            return custom_message({'message': 'Not authorized'}, 401)
        else:
            return custom_message({'message': 'Something went wrong'}, 500)


# True for easy debugging with pycharm
app.run(host='0.0.0.0', debug=False, port=8443,
        ssl_context=(certs_location + 'api.crt', certs_location + 'api.key'))
