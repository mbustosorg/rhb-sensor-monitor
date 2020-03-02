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
import datetime
import time
import json
from time import sleep

import pandas as pd

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

persist_period = datetime.timedelta(seconds=600)
pressure_records = pd.DataFrame(columns=['timestamps', 'level'])
position_records = pd.DataFrame(columns=['timestamps', 'lat', 'lon'])
imu_records = pd.DataFrame(columns=['timestamps', 'heading'])
last_persist = datetime.datetime.now()


def initialize_histories():
    """ Re-initialize history records """
    global pressure_records
    global position_records
    global imu_records
    global last_persist
    
    pressure_records = pd.DataFrame(columns=['timestamps', 'level'])
    position_records = pd.DataFrame(columns=['timestamps', 'lat', 'lon'])
    imu_records = pd.DataFrame(columns=['timestamps', 'heading'])
    last_persist = datetime.datetime.now()
    
    
def send_position_update(gps):
    """ Broadcast the current position """
    global position_records

    if ('n/a' not in str(gps.TPV['lat']) and 'n/a' not in str(gps.TPV['lon'])):
        lat = float(gps.TPV['lat'])
        lon = float(gps.TPV['lon'])
        if (len(position_records['timestamps']) == 0) or \
           (abs(lon - position_records['lon'].iloc[-1]) > 0.000001) or \
           (abs(lat - position_records['lat'].iloc[-1]) > 0.000001):
            msg = osc_message_builder.OscMessageBuilder(address="/position")
            if len(position_records['timestamps']) > 0:
                lat = position_records['lat'].iloc[-1] + 0.00001
            msg.add_arg(lat)
            msg.add_arg(lon)
            built = msg.build()
            display_client.send(built)
            mobile_client.send(built)
            logger.info(fr"Latitude = {data_stream.TPV['lat']}")
            logger.info(fr"Latitude = {data_stream.TPV['lon']}")
            position_records = position_records.append({'timestamps' : datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f'),
                                                        'lat' : lat,
                                                        'lon' : lon}, ignore_index=True)


def send_pressure_update(pressure):
    """ Broadcast the current accumulator pressure """
    global pressure_records

    if (len(pressure_records['timestamps']) == 0) or (abs(pressure - pressure_records['level'].iloc[-1]) > 300):
        msg = osc_message_builder.OscMessageBuilder(address='/pressure')
        msg.add_arg(pressure)
        built = msg.build()
        pressure_client.send(built)
        display_client.send(built)
        mobile_client.send(built)
        logger.info(f'Pressure = {pressure}')
        pressure_records = pressure_records.append({'timestamps' : datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f'),
                                                    'level' : pressure}, ignore_index=True)


def send_imu_update(imu_state):
    """ Broadcast the current IMU state """
    global imu_records
    
    heading = imu_state['heading']['heading']
    if (len(imu_records['timestamps']) == 0) or (abs(heading - imu_records['heading'].iloc[-1]) > 1.0):
        msg = osc_message_builder.OscMessageBuilder(address='/imu')
        msg.add_arg(json.dumps(imu_state))
        display_client.send(msg.build())
        imu_records = imu_records.append({'timestamps' : datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f'),
                                          'heading' : heading}, ignore_index=True)


def persist_histories():
    """ Store off histories periodically """ 
    if datetime.datetime.now() - last_persist > persist_period:
        timestamp = str(int(datetime.datetime.now().timestamp()))
        position_records.to_csv('/home/mauricio/data/positions_' + timestamp + '.csv')
        pressure_records.to_csv('/home/mauricio/data/pressure_' + timestamp + '.csv')
        imu_records.to_csv('/home/mauricio/data/heading_' + timestamp + '.csv')
        initialize_histories()


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
            persist_histories()
            send_pressure_update(pressure_sensor.read_pressure())
            imu_state = IMU_state()
            send_imu_update(imu_state)
            if new_data:
                data_stream.unpack(new_data)
                #logger.info(imu_state)
                send_position_update(data_stream)
                    
