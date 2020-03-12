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

import pydevd_pycharm
from gps3 import gps3
from pythonosc import osc_message_builder
from pythonosc import udp_client

from rhb_sensor_monitor import pressure_sensor, poof_track as pt, temperature_sensor, metric_logging as ml
from rhb_sensor_monitor.imu.berryIMU import IMU_state

pydevd_pycharm.settrace('10.0.1.30', port=12345, stdoutToServer=True, stderrToServer=True)

gps_socket = gps3.GPSDSocket()
data_stream = gps3.DataStream()

FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

gps_socket.connect()
gps_socket.watch()

TEMP_PERIOD = datetime.timedelta(seconds=300)

poof_track = pt.PoofTrack()
metrics = ml.MetricLogging(datetime.timedelta(seconds=600), '/home/mauricio/data')


def handle_exception(func):
    """ Handle exception when interacting with peripherals """
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as exception:
            logger.error(exception)
    return wrapper


def broadcast(endpoint, value):
    """ Broadcast `value' """
    msg = osc_message_builder.OscMessageBuilder(address=endpoint)
    msg.add_arg(value)
    built = msg.build()
    display_client.send(built)
    mobile_client.send(built)
    pressure_client.send(built)


@handle_exception
def send_position_update(gps):
    """ Broadcast the current position """
    if 'n/a' not in str(gps.TPV['lat']) and 'n/a' not in str(gps.TPV['lon']):
        lat = float(gps.TPV['lat'])
        lon = float(gps.TPV['lon'])
        if metrics.position.empty or \
                (abs(lon - metrics.position['lon'].iloc[-1]) > 0.00005) or \
                (abs(lat - metrics.position['lat'].iloc[-1]) > 0.00005):
            if not metrics.position.empty:
                lat = metrics.position['lat'].iloc[-1] + 0.00001
            broadcast("/position/lat", lat)
            broadcast("/position/lon", lon)
            metrics.position = metrics.position.append(
                {'timestamp': metrics.now_string(),
                 'lat': lat,
                 'lon': lon}, ignore_index=True)
            logger.info(fr"Latitude = {data_stream.TPV['lat']}")
            logger.info(fr"Latitude = {data_stream.TPV['lon']}")


@handle_exception
def send_pressure_update():
    """ Broadcast the current accumulator pressure """
    pressure = pressure_sensor.read_pressure()
    poof_track.add_observation(pressure)
    if metrics.pressure.empty or poof_track.poofing():
        broadcast('/pressure', float(pressure))
        metrics.pressure = metrics.pressure.append(
            {'timestamp': metrics.now_string(),
             'level': pressure}, ignore_index=True)
        broadcast('/poof_count', float(poof_track.poof_count))
        logger.info(f'Pressure = {pressure}')
    elif poof_track.poofing():
        poof_track.stop()
        broadcast('/poof_seconds', poof_track.poof_time)


@handle_exception
def send_imu_update():
    """ Broadcast the current IMU state """
    updated_imu_state = IMU_state()
    heading = updated_imu_state['heading']['heading']
    if metrics.imu.empty or (abs(heading - metrics.imu['heading'].iloc[-1]) > 1.0):
        broadcast('/imu', json.dumps(updated_imu_state))
        metrics.imu = metrics.imu.append({'timestamp': metrics.now_string(), 'heading': heading}, ignore_index=True)
        logger.info(f'Heading = {heading}')


@handle_exception
def send_temp_update():
    """ Broadcast the current temperature """
    if not metrics.temp.empty:
        last_timestamp = datetime.datetime.now().strptime(metrics.temp['timestamp'].iloc[-1], '%Y-%m-%dT%H:%M:%S.%f')
    if metrics.temp.empty or datetime.datetime.now() - last_timestamp > TEMP_PERIOD:
        updated_temp = temperature_sensor.current_temp()
        if updated_temp[0] > 0.0 and \
                (metrics.temp.empty or (abs(updated_temp[1] - metrics.temp['temp_f'].iloc[-1]) > 1.0)):
            broadcast('/temperature', updated_temp[1])
            metrics.temp = metrics.temp.append(
                {'timestamp': metrics.now_string(),
                 'temp_f': updated_temp[1]}, ignore_index=True)
            logger.info(f'Temperature = {updated_temp}')


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
        try:
            for new_data in gps_socket:
                metrics.persist()

                send_pressure_update()
                send_imu_update()
                send_temp_update()
                if new_data:
                    data_stream.unpack(new_data)
                    send_position_update(data_stream)
        except Exception as exception:
            logger.error(exception)
