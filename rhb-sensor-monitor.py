"""
    Copyright (C) 2020 Mauricio Bustos (m@bustos.org)
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

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
    """ Broadcast the current position """
    msg = osc_message_builder.OscMessageBuilder(address="/position")
    msg.add_arg(data_stream.TPV['lat'])
    msg.add_arg(data_stream.TPV['lon'])
    built = msg.build()
    display_client.send(built)
    mobile_client.send(built)
    logger.info(fr"Latitude = {data_stream.TPV['lat']}")
    logger.info(fr"Latitude = {data_stream.TPV['lon']}")


def send_pressure_update(pressure):
    """ Broadcast the current accumulator pressure """
    global last_pressure

    if abs(pressure - last_pressure) > 300:
        last_pressure = pressure
        msg = osc_message_builder.OscMessageBuilder(address='/pressure')
        msg.add_arg(pressure)
        built = msg.build()
        pressure_client.send(built)
        display_client.send(built)
        mobile_client.send(built)
        logger.info(f'Pressure = {pressure}')


def send_imu_update(imu_state):
    """ Broadcast the current IMU state """
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
    parser.add_argument('--mobile_ip', default='10.0.1.59',
                        help='The ip of the mobile osc display')
    parser.add_argument('--mobile_port', type=int, default=10004,
                        help='The port the mobile osc display is listening on')
    args = parser.parse_args()

    display_client = udp_client.UDPClient(args.display_ip, args.display_port)
    pressure_client = udp_client.UDPClient(args.pressure_ip, args.pressure_port)
    mobile_client = udp_client.UDPClient(args.mobile_ip, args.mobile_port)

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
                    
