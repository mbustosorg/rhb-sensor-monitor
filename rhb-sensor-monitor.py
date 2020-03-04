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

import argparse
import datetime
import json
import logging
import pandas as pd
from gps3 import gps3
from pythonosc import osc_message_builder
from pythonosc import udp_client

import pressure_sensor
import temperature_sensor
from imu.berryIMU import IMU_state

import pydevd_pycharm

pydevd_pycharm.settrace('10.0.1.30', port=12345, stdoutToServer=True, stderrToServer=True)

gps_socket = gps3.GPSDSocket()
data_stream = gps3.DataStream()

FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

gps_socket.connect()
gps_socket.watch()

PERSIST_PERIOD = datetime.timedelta(seconds=600)
TEMP_PERIOD = datetime.timedelta(seconds=300)


def handle_exception(func):
    """ Handle exception when interacting with peripherals """

    def wrapper():
        try:
            func()
        except Exception as exception:
            logger.error(exception)

    return wrapper


def now():
    """ Formatted date string """
    return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')


@handle_exception
def send_position_update(gps, history):
    """ Broadcast the current position """
    position_records = history['position']

    if 'n/a' not in str(gps.TPV['lat']) and 'n/a' not in str(gps.TPV['lon']):
        lat = float(gps.TPV['lat'])
        lon = float(gps.TPV['lon'])
        if position_records['timestamps'].empty or \
                (abs(lon - position_records['lon'].iloc[-1]) > 0.000001) or \
                (abs(lat - position_records['lat'].iloc[-1]) > 0.000001):
            if not position_records['timestamps'].empty:
                lat = position_records['lat'].iloc[-1] + 0.00001
            msg = osc_message_builder.OscMessageBuilder(address="/position")
            msg.add_arg(lat)
            msg.add_arg(lon)
            built = msg.build()
            display_client.send(built)
            mobile_client.send(built)
            logger.info(fr"Latitude = {data_stream.TPV['lat']}")
            logger.info(fr"Latitude = {data_stream.TPV['lon']}")
            history['position'] = position_records.append(
                {'timestamps': now(),
                 'lat': lat,
                 'lon': lon}, ignore_index=True)


@handle_exception
def send_pressure_update(history):
    """ Broadcast the current accumulator pressure """
    pressure_records = history['pressure']
    pressure = pressure_sensor.read_pressure()
    if pressure_records['timestamps'].empty or (abs(pressure - pressure_records['level'].iloc[-1]) > 300):
        msg = osc_message_builder.OscMessageBuilder(address='/pressure')
        msg.add_arg(pressure)
        built = msg.build()
        pressure_client.send(built)
        display_client.send(built)
        mobile_client.send(built)
        logger.info(f'Pressure = {pressure}')
        history['pressure'] = pressure_records.append(
            {'timestamps': now(),
             'level': pressure}, ignore_index=True)


@handle_exception
def send_imu_update(history):
    """ Broadcast the current IMU state """
    imu_records = history['imu']
    updated_imu_state = IMU_state()
    heading = updated_imu_state['heading']['heading']
    if imu_records['timestamps'].empty or (abs(heading - imu_records['heading'].iloc[-1]) > 1.0):
        msg = osc_message_builder.OscMessageBuilder(address='/imu')
        msg.add_arg(json.dumps(updated_imu_state))
        built = msg.build()
        display_client.send(built)
        mobile_client.send(built)
        history['imu'] = imu_records.append({'timestamps': now(),
                                             'heading': heading}, ignore_index=True)


@handle_exception
def send_temp_update(history):
    """ Broadcast the current temperature """
    temp_records = history['temp']
    if not temp_records['timestamps'].empty:
        last_timestamp = datetime.datetime.now().strptime(temp_records['temp_f'].iloc[-1], '%Y-%m-%dT%H:%M:%S.%f')
    if temp_records['timestamps'].empty or datetime.datetime.now().timestamp() - last_timestamp > TEMP_PERIOD:
        updated_temp = temperature_sensor.current_temp()
        if updated_temp[0] > 0.0 and \
                (temp_records['timestamps'].empty or (abs(updated_temp[1] - temp_records['temp_f'].iloc[-1]) > 1.0)):
            logger.info(f'Temperature = {updated_temp}')
            msg = osc_message_builder.OscMessageBuilder(address='/temperature')
            msg.add_arg(updated_temp[1])
            built = msg.build()
            display_client.send(built)
            mobile_client.send(built)
            history['temp'] = temp_records.append({'timestamps': now(),
                                                   'temp_f': updated_temp[1]}, ignore_index=True)


def persist_histories(history):
    """ Store off histories periodically """
    if datetime.datetime.now() - history['last_persist'] > PERSIST_PERIOD:
        timestamp = str(int(datetime.datetime.now().timestamp()))
        history['position'].to_csv('/home/mauricio/data/positions_' + timestamp + '.csv')
        history['pressure'].to_csv('/home/mauricio/data/pressure_' + timestamp + '.csv')
        history['imu'].to_csv('/home/mauricio/data/heading_' + timestamp + '.csv')
        history['temp'].to_csv('/home/mauricio/data/temp_' + timestamp + '.csv')
        return initialized_histories()
    return history


def initialized_histories():
    """ Re-initialize history records """
    return {'last_persist': datetime.datetime.now(),
            'pressure': pd.DataFrame(columns=['timestamps', 'level']),
            'position': pd.DataFrame(columns=['timestamps', 'lat', 'lon']),
            'imu': pd.DataFrame(columns=['timestamps', 'heading']),
            'temp': pd.DataFrame(columns=['timestamps', 'temp_f'])}


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

    data_history = initialized_histories()
    while True:
        try:
            for new_data in gps_socket:
                data_history = persist_histories(data_history)

                send_pressure_update(data_history)
                send_imu_update(data_history)
                send_temp_update(data_history)
                if new_data:
                    data_stream.unpack(new_data)
                    send_position_update(data_stream, data_history)
        except Exception as exception:
            logger.error(exception)
