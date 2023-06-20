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
from logging.handlers import RotatingFileHandler
import os
import shutil

import pandas as pd
import piglow
from gps3 import gps3
from pythonosc import osc_message_builder
from pythonosc import udp_client
from digi.xbee.devices import XBeeDevice, RemoteXBeeDevice, XBee64BitAddress

XBEE_COORDINATOR = "0013A20041CB4F87"
XBEE_ROUTER = "0013A20041CB7786"
radio = XBeeDevice("/dev/ttyUSB0", 9600)
radio.open()
base_xbee = RemoteXBeeDevice(radio, XBee64BitAddress.from_hex_string(XBEE_ROUTER))

from rhb_sensor_monitor import (
    pressure_sensor,
    poof_track as pt,
    temperature_sensor,
    metric_logging as ml,
)
from rhb_sensor_monitor.imu.berryIMU import IMU_state

gps_socket = gps3.GPSDSocket()
data_stream = gps3.DataStream()

FORMAT = "%(asctime)-15s|%(module)s|%(lineno)d|%(message)s"
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)

FILE_HANDLER = RotatingFileHandler("rhb-sensor-monitor.log", maxBytes=40000, backupCount=5)
FILE_HANDLER.setLevel(logging.INFO)
FILE_HANDLER.setFormatter(FORMAT)
logger.addHandler(FILE_HANDLER)

gps_socket.connect()
gps_socket.watch()

TEMP_PERIOD = datetime.timedelta(seconds=60)

poof_track = pt.PoofTrack()
metrics = ml.MetricLogging(
    datetime.timedelta(seconds=15 * 60),
    datetime.timedelta(seconds=5),
    "/home/pi/development/data",
)


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
    if "pressure" in endpoint or "temperature" in endpoint:
        telemetry_1_client.send(built)


def pi_temp() -> float:
    """Onboard CPU temperature"""
    temp = os.popen("cat /sys/class/thermal/thermal_zone0/temp").read()
    return float(int(float(temp) / 1000.0))


@handle_exception
def update_position(gps):
    """ Broadcast the current position """
    if "n/a" not in str(gps.TPV["lat"]) and "n/a" not in str(gps.TPV["lon"]):
        lat = float(gps.TPV["lat"])
        lon = float(gps.TPV["lon"])
        alt = float(gps.TPV["alt"])
        if (
            metrics.position.empty
            or (abs(lon - metrics.position["lon"].iloc[-1]) > 0.00005)
            or (abs(lat - metrics.position["lat"].iloc[-1]) > 0.00005)
            or (abs(alt - metrics.position["alt"].iloc[-1]) > 5.0)
        ):
            broadcast("/position/lat", lat)
            broadcast("/position/lon", lon)
            broadcast("/position/alt", alt)
            metrics.position = pd.concat(
                [
                    metrics.position,
                    pd.DataFrame.from_records(
                        [{"timestamp": metrics.now_string(), "lat": lat, "lon": lon, "alt": alt}]
                    ),
                ]
            )
            logger.info(fr"Latitude = {data_stream.TPV['lat']}")
            logger.info(fr"Longitude = {data_stream.TPV['lon']}")
            logger.info(fr"Altitude = {data_stream.TPV['alt']}")


@handle_exception
def update_pressure():
    """ Broadcast the current accumulator pressure """
    pressure = poof_track.pressure_from_raw(pressure_sensor.read_pressure())
    broadcast("/pressure", float(round(float(poof_track.last_pressure))))
    poof_track.add_observation(pressure)
    if metrics.pressure.empty or poof_track.poofing():
        piglow.red(64)
        piglow.show()
        metrics.pressure = pd.concat(
            [
                metrics.pressure,
                pd.DataFrame.from_records(
                    [{"timestamp": metrics.now_string(), "level": pressure}]
                ),
            ]
        )
        #broadcast("/poof_count", float(poof_track.poof_count))
        #logger.info(f"Pressure = {pressure}")
    elif not poof_track.poofing():
        piglow.red(0)
        piglow.show()


@handle_exception
def update_imu():
    """ Broadcast the current IMU state """
    updated_imu_state = IMU_state()
    heading = float(round(float(updated_imu_state["heading"]["tiltCompensatedHeading"])))
    if metrics.imu.empty or (abs(heading - metrics.imu["heading"].iloc[-1]) > 1.5):
        broadcast("/imu", json.dumps(updated_imu_state))
        broadcast("/heading", heading)
        metrics.imu = pd.concat(
            [
                metrics.imu,
                pd.DataFrame.from_records(
                    [{"timestamp": metrics.now_string(), "heading": heading}]
                ),
            ]
        )
        logger.info(f"Heading = {heading}")


@handle_exception
def update_temperature():
    """ Broadcast the current temperature """
    if not metrics.temp.empty:
        last_timestamp = datetime.datetime.strptime(
            metrics.temp["timestamp"].iloc[-1], "%Y-%m-%dT%H:%M:%S.%f"
        )
    if metrics.temp.empty or (datetime.datetime.now() - last_timestamp > TEMP_PERIOD):
        updated_temp = temperature_sensor.current_temp()
        broadcast("/temperature", float(int(updated_temp[1])))
        metrics.temp = pd.concat(
            [
                metrics.temp,
                pd.DataFrame.from_records(
                    [{"timestamp": metrics.now_string(), "temp_f": updated_temp[1], "temp_cpu": pi_temp()}]
                ),
            ]
        )
        logger.info(f"Temperature = {updated_temp[1]}")


@handle_exception
def update_disk_usage():
    """ Broadcast the current free disk percentage """
    stat = shutil.disk_usage("/")
    free = int(float(stat.free) / float(stat.total) * 100.0)
    if metrics.disk.empty or (abs(free - metrics.disk["free"].iloc[-1]) > 0.0):
        broadcast("/free_disk", float(free))
        metrics.disk = pd.concat(
            [
                metrics.disk,
                pd.DataFrame.from_records(
                    [{"timestamp": metrics.now_string(), "free": free}]
                ),
            ]
        )
        logger.info(f"Free disk = {free}")


@handle_exception
def broadcast_last():
    """ Periodically broadcast last set of data """
    if metrics.time_to_broadcast_by_radio():
        try:
            radio.send_data_async(base_xbee, f"{metrics.position['lat'].iloc[-1]},{metrics.position['lon'].iloc[-1]}")
        except Exception as exception:
            logger.error(str(exception))
    if metrics.time_to_broadcast():
        logger.debug("State broadcast")
        if metrics.position.shape[0] > 0:
            broadcast("/position/lat", float(metrics.position["lat"].iloc[-1]))
            broadcast("/position/lon", float(metrics.position["lon"].iloc[-1]))
        if metrics.imu.shape[0] > 0:
            broadcast("/heading", float(metrics.imu["heading"].iloc[-1]))
        broadcast("/pressure", float(round(float(poof_track.last_pressure))))
        if metrics.temp.shape[0] > 0:
            broadcast("/temperature", float(int(metrics.temp["temp_f"].iloc[-1])))
            broadcast("/temperature_cpu", float(metrics.temp["temp_cpu"].iloc[-1]))
        if metrics.disk.shape[0] > 0:
            broadcast("/free_disk", float(metrics.disk["free"].iloc[-1]))
        broadcast("/poof_count", float(poof_track.poof_count))
        broadcast("/poof_seconds", float(poof_track.poof_time))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--display_ip", default="127.0.0.1", help="The ip of the display osc server"
    )
    parser.add_argument(
        "--display_port",
        type=int,
        default=10002,
        help="The port the display osc server is listening on",
    )
    parser.add_argument(
        "--pressure_ip", default="192.168.1.4", help="The ip of the dial server"
    )
    parser.add_argument(
        "--pressure_port",
        type=int,
        default=8888,
        help="The port the pressure osc server is listening on",
    )
    parser.add_argument(
        "--telemetry_1_ip", default="192.168.1.8", help="The ip of the first telemetry server"
    )
    parser.add_argument(
        "--telemetry_1_port",
        type=int,
        default=8888,
        help="The port the first telemetry server is listening on",
    )
    parser.add_argument(
        "--mobile_ip", default="192.168.1.5", help="The ip of the mobile osc display"
    )
    parser.add_argument(
        "--mobile_port",
        type=int,
        default=8888,
        help="The port the mobile osc display is listening on",
    )
    args = parser.parse_args()

    display_client = udp_client.UDPClient(args.display_ip, args.display_port)
    pressure_client = udp_client.UDPClient(args.pressure_ip, args.pressure_port)
    mobile_client = udp_client.UDPClient(args.mobile_ip, args.mobile_port)
    telemetry_1_client = udp_client.UDPClient(args.telemetry_1_ip, args.telemetry_1_port)
    watchdog_led = False
    hour = -1
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
                try:
                    date = datetime.datetime.strptime(data_stream.TPV["time"], "%Y-%m-%dT%H:%M:%S.%f%z")
                    if hour != date.hour:
                        os.system(f'sudo date -s "{data_stream.TPV["time"]}"')
                        hour = date.hour
                except:
                    pass
                update_position(data_stream)
                if not watchdog_led:
                    piglow.blue(64)
                else:
                    piglow.blue(0)
                watchdog_led = not watchdog_led
            broadcast_last()
        except Exception as exception:
            logger.error(exception)
