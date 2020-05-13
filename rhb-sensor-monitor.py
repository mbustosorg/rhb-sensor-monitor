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
import shutil
import traceback

import piglow
import pydevd_pycharm
from gps3 import gps3
from pythonosc import osc_message_builder
from pythonosc import udp_client

from rhb_sensor_monitor import pressure_sensor, poof_track as pt, temperature_sensor, metric_logging as ml
from rhb_sensor_monitor.imu.berryIMU import IMU_state

try:
    pydevd_pycharm.settrace('10.0.1.30', port=12345, stdoutToServer=True, stderrToServer=True)
except:
    pass

gps_socket = gps3.GPSDSocket()
data_stream = gps3.DataStream()

FORMAT = '%(asctime)-15s %(name)s %(lineno)d %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)

gps_socket.connect()
gps_socket.watch()

TEMP_PERIOD = datetime.timedelta(seconds=6 * 60) # 10 Observations per hour
TEMP_PERIOD = datetime.timedelta(seconds=60) # 10 Observations per hour

poof_track = pt.PoofTrack()
metrics = ml.MetricLogging(datetime.timedelta(seconds=30 * 60), datetime.timedelta(seconds=10), '/home/mauricio/data')
metrics = ml.MetricLogging(datetime.timedelta(seconds=30 * 60), datetime.timedelta(seconds=1), '/home/mauricio/data')


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
def update_position(gps):
    """ Broadcast the current position """
    if 'n/a' not in str(gps.TPV['lat']) and 'n/a' not in str(gps.TPV['lon']):
        lat = float(gps.TPV['lat'])
        lon = float(gps.TPV['lon'])
        if metrics.position.empty or \
                (abs(lon - metrics.position['lon'].iloc[-1]) > 0.0005) or \
                (abs(lat - metrics.position['lat'].iloc[-1]) > 0.0005):
            if not metrics.position.empty:
                lat = metrics.position['lat'].iloc[-1] + 0.00001
            broadcast('/position/lat', lat)
            broadcast('/position/lon', lon)
            metrics.position = metrics.position.append(
                {'timestamp': metrics.now_string(),
                 'lat': lat,
                 'lon': lon}, ignore_index=True)
            logger.info(fr"Latitude = {data_stream.TPV['lat']}")
            logger.info(fr"Latitude = {data_stream.TPV['lon']}")


@handle_exception
def update_pressure():
    """ Broadcast the current accumulator pressure """
    pressure = pressure_sensor.read_pressure()
    poof_track.add_observation(pressure)
    if metrics.pressure.empty or poof_track.poofing():
        piglow.red(64)
        piglow.show()
        broadcast('/pressure', float(pressure))
        metrics.pressure = metrics.pressure.append(
            {'timestamp': metrics.now_string(),
             'level': pressure}, ignore_index=True)
        broadcast('/poof_count', float(poof_track.poof_count))
        logger.info(f'Pressure = {pressure}')
    elif not poof_track.poofing():
        piglow.red(0)
        piglow.show()
        poof_track.stop()
        broadcast('/poof_seconds', float(poof_track.poof_time))
        

@handle_exception
def update_imu():
    """ Broadcast the current IMU state """
    updated_imu_state = IMU_state()
    heading = updated_imu_state['heading']['heading']
    if metrics.imu.empty or (abs(heading - metrics.imu['heading'].iloc[-1]) > 1.0):
        broadcast('/imu', json.dumps(updated_imu_state))
        broadcast('/heading', heading)
        metrics.imu = metrics.imu.append({'timestamp': metrics.now_string(), 'heading': heading}, ignore_index=True)
        logger.info(f'Heading = {heading}')


@handle_exception
def update_temperature():
    """ Broadcast the current temperature """
    if not metrics.temp.empty:
        last_timestamp = datetime.datetime.strptime(metrics.temp['timestamp'].iloc[-1], '%Y-%m-%dT%H:%M:%S.%f')
    if metrics.temp.empty or (datetime.datetime.now() - last_timestamp > TEMP_PERIOD):
        updated_temp = temperature_sensor.current_temp()
        broadcast('/temperature', float(int(updated_temp[1])))
        metrics.temp = metrics.temp.append(
            {'timestamp': metrics.now_string(),
             'temp_f': updated_temp[1]}, ignore_index=True)
        logger.info(f'Temperature = {updated_temp[1]}')

        
@handle_exception
def update_disk_usage():
    """ Broadcast the current free disk percentage """
    stat = shutil.disk_usage('/')
    free = int(float(stat.free) / float(stat.total) * 100.0)
    if metrics.disk.empty or (abs(free - metrics.disk['free'].iloc[-1]) > 0.0):
        broadcast('/free_disk', float(free))
        metrics.disk = metrics.disk.append({'timestamp': metrics.now_string(), 'free': free}, ignore_index=True)
        logger.info(f'Free disk = {free}')


@handle_exception
def broadcast_last():
    """ Periodically broadcast last set of data """
    if metrics.time_to_broadcast():
        logger.info('State broadcast')
        broadcast('/position/lat', float(metrics.position['lat'].iloc[-1]))
        broadcast('/position/lon', float(metrics.position['lon'].iloc[-1]))
        broadcast('/heading', float(metrics.imu['heading'].iloc[-1]))
        broadcast('/pressure', float(poof_track.last_pressure))
        broadcast('/temperature', float(metrics.temp['temp_f'].iloc[-1]))
        broadcast('/free_disk', float(metrics.disk['free'].iloc[-1]))
        broadcast('/poof_count', float(poof_track.poof_count))
        broadcast('/poof_seconds', float(poof_track.poof_time))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--display_ip', default='127.0.0.1',
                        help='The ip of the display osc server')
    parser.add_argument('--display_port', type=int, default=10002,
                        help='The port the display osc server is listening on')
    parser.add_argument('--pressure_ip', default='10.0.1.32',
                        help='The ip of the pressure osc server')
    parser.add_argument('--pressure_port', type=int, default=10003,
                        help='The port the pressure osc server is listening on')
    parser.add_argument('--mobile_ip', default='10.0.1.2',
                        help='The ip of the mobile osc display')
    parser.add_argument('--mobile_port', type=int, default=10004,
                        help='The port the mobile osc display is listening on')
    args = parser.parse_args()

    display_client = udp_client.UDPClient(args.display_ip, args.display_port)
    pressure_client = udp_client.UDPClient(args.pressure_ip, args.pressure_port)
    mobile_client = udp_client.UDPClient(args.mobile_ip, args.mobile_port)

    while True:
        try:
            metrics.persist()
            update_pressure()
            update_imu()
            update_temperature()
            update_disk_usage()
            new_data = gps_socket.next()
            if new_data:
                data_stream.unpack(new_data)
                update_position(data_stream)
            broadcast_last()
        except Exception as exception:
            logger.error(exception)
