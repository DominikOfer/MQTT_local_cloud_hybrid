#!python3
import paho.mqtt.client as mqtt
import time

def connect_feedback(client, userdata, flags, rc):
    if rc==0:
        client.connected_flag=True #set flag
        print("connected OK Returned code=",rc)
    else:
        print("Bad connection Returned code=",rc)

mqtt.Client.connected_flag=False #create flag in class
broker="broker.emqx.io" #public test broker

client = mqtt.Client("testclient01")
client.on_connect=connect_feedback

client.loop_start()
print("connecting to broker ",broker)

try:
    client.connect(broker) #connect to broker
except:
    print("connection failed")
    exit(1) #Should quit or raise flag to quit or retry

while not client.connected_flag: #wait in loop
    print("In wait loop")
    time.sleep(1)
print("in Main Loop")
client.loop_stop()  #Stop loop
client.disconnect() #disconnect