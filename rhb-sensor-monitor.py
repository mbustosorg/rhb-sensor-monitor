""" Monitor IMU """

import piglow
import argparse
import logging
import time
import json
from time import sleep

import pressure_sensor

from pythonosc import udp_client
from pythonosc import osc_bundle_builder
from pythonosc import osc_message_builder

from gps3 import gps3
from imu.berryIMU import IMU_state

gps_socket = gps3.GPSDSocket()
data_stream = gps3.DataStream()

FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger('IMU')
logger.setLevel(logging.INFO)

gps_socket.connect()
gps_socket.watch()

last_message_time = int(time.time())
last_pressure = 0

def send_position_update(data_stream):
    msg = osc_message_builder.OscMessageBuilder(address="/position")
    msg.add_arg(data_stream.TPV['lat'])
    msg.add_arg(data_stream.TPV['lon'])
    display_client.send(msg.build())
    logger.info(fr"Latitude = {data_stream.TPV['lat']}")
    logger.info(fr"Latitude = {data_stream.TPV['lon']}")


def send_pressure_update(pressure):
    global last_pressure
    
    if abs(pressure - last_pressure) > 300:
        last_pressure = pressure
        msg = osc_message_builder.OscMessageBuilder(address='/pressure')
        msg.add_arg(pressure)
        pressure_client.send(msg.build())
        display_client.send(msg.build())
        logger.info(f'Pressure = {pressure}')


def send_imu_update(imu_state):
    #logger.info(f'IMU = {imu_state}')
    msg = osc_message_builder.OscMessageBuilder(address='/imu')
    msg.add_arg(json.dumps(imu_state))
    display_client.send(msg.build())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--display_ip', default='127.0.0.1',
                        help='The ip of the display osc server')
    parser.add_argument('--display_port', type=int, default=10002,
                        help='The port the display osc server is listening on')
    parser.add_argument('--pressure_ip', default='10.0.1.58',
                        help='The ip of the pressure osc server')
    parser.add_argument('--pressure_port', type=int, default=10003,
                        help='The port the pressure osc server is listening on')
    args = parser.parse_args()

    display_client = udp_client.UDPClient(args.display_ip, args.display_port)
    pressure_client = udp_client.UDPClient(args.pressure_ip, args.pressure_port)

    while True:
        for new_data in gps_socket:
            imu_state = IMU_state()
            send_imu_update(imu_state)
            send_pressure_update(pressure_sensor.read_pressure())
            if new_data:
                current_time = int(time.time())
                if last_message_time < current_time:
                    data_stream.unpack(new_data)
                    logger.info(imu_state)
                    send_position_update(data_stream)
                    last_message_time = current_time
                    
