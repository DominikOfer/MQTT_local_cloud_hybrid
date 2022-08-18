#!/usr/bin/env python
# encoding: utf-8
import json
import paho.mqtt.publish as publish
import paho.mqtt.subscribe as subscribe
from paho.mqtt import MQTTException
from flask import Flask, jsonify, render_template, request, make_response

app = Flask(__name__)
broker = '10.0.0.100'


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
        # ON SUBSCRIBE YOU ONLY GET LAST RETAINED VALUE!!!! MUST NOT BE CURRENT VALUE!!!
        msg = subscribe.simple(topic + '/' + sensor, qos=1, hostname=broker, client_id='mqtt_api')
        return jsonify({'topic': msg.topic, 'payload': msg.payload})
    else:
        return custom_message({'message': 'Sensor and topic are required'}, 400)


@app.route('/api/control', methods=['POST'])
def control_sensor():
    try:
        record = json.loads(request.data)
        if 'sensor' in record and 'topic' in record and 'message' in record:
            publish.single(record['topic']+'/'+record['sensor']+'/'+'control', record['message'], hostname=broker, client_id='mqtt_api', qos=1)
            return jsonify(record)
        else:
            return custom_message({'message': 'Sensor, topic and message are required'}, 400)
    except ValueError as e:
        return custom_message({'message': 'Invalid JSON'}, 400)
    except MQTTException as e:
        return custom_message({'message': 'Error in MQTT functionality'}, 500)


# True for easy debugging with pycharm
app.run(host='0.0.0.0', port=5000, debug=False)
