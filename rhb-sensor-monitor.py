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
import asyncio
import datetime
import json
import logging
from logging import Logger
from logging.handlers import RotatingFileHandler
import os
import shutil

import pandas as pd
import piglow
from gps3 import gps3
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_message_builder
from pythonosc import udp_client
from digi.xbee.devices import XBeeDevice, RemoteXBeeDevice, XBee64BitAddress
import geopy.distance

import rhb_sensor_monitor.alternating_sensor as AS

XBEE_COORDINATOR = "0013A20041CB4F87"
XBEE_ROUTER = "0013A20041CB7786"
radio = XBeeDevice("/dev/ttyUSB0", 9600)
radio.open()
base_xbee = RemoteXBeeDevice(radio, XBee64BitAddress.from_hex_string(XBEE_ROUTER))

from rhb_sensor_monitor import (
    pressure_sensor,
    pressure_health as ph,
    poof_track as pt,
    metric_logging as ml,
)
from rhb_sensor_monitor.imu.berryIMU import IMU_state

gps_socket = gps3.GPSDSocket()
data_stream = gps3.DataStream()

FORMAT = "%(asctime)-15s %(message)s"
logging.basicConfig(format=FORMAT)
LOGGER: Logger = logging.getLogger("rhb-sensor-monitor")
LOGGER.setLevel(logging.INFO)
LOG_FORMAT = logging.Formatter(FORMAT)

FILE_HANDLER = RotatingFileHandler("rhb-sensor-monitor.log", maxBytes=200000, backupCount=5)
FILE_HANDLER.setLevel(logging.INFO)
FILE_HANDLER.setFormatter(LOG_FORMAT)
LOGGER.addHandler(FILE_HANDLER)

FORMAT = "%(asctime)-15s|%(module)s|%(lineno)d|%(message)s"
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)

gps_socket.connect()
gps_socket.watch()

PRESSURE_PERIOD = datetime.timedelta(seconds=0.5)
last_pressure_timestamp = datetime.datetime.now()

poof_track = pt.PoofTrack()
pressure_health = ph.PressureHealth()
water_state = {"/temperature": 0.0, "/water_heater": 0.0}
metrics = ml.MetricLogging(
    datetime.timedelta(seconds=15 * 60),
    datetime.timedelta(seconds=5),
    "/home/pi/development/data",
)

#oil_pressure_sensor = AS.AlternatingSensor(29, "oil_pressure", 1000)
#speedometer_sensor = AS.AlternatingSensor(31, "speedometer", 1000)


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
    try:
        for client in osc_clients:
            client.send(built)
    except Exception as e:
        print(e)


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
            if not metrics.position.empty:
                coords_1 = (metrics.position["lat"].iloc[-1], metrics.position["lon"].iloc[-1])
                coords_2 = (lat, lon)
                distance = geopy.distance.geodesic(coords_1, coords_2).mi
                timestamp_diff = datetime.datetime.now() - datetime.datetime.strptime(metrics.position["timestamp"].iloc[-1], "%Y-%m-%dT%H:%M:%S.%f")
                inferred_speed = distance / timestamp_diff.seconds * 3600
            else:
                inferred_speed = 0.0

            broadcast("/position/lat", lat)
            broadcast("/position/lon", lon)
            broadcast("/position/alt", alt)
            broadcast("/position/inferred_speed", inferred_speed)

            metrics.position = pd.concat(
                [
                    metrics.position,
                    pd.DataFrame.from_records(
                        [{"timestamp": metrics.now_string(), "lat": lat, "lon": lon, "alt": alt, "speed": inferred_speed}]
                    ),
                ]
            )
            logger.info(fr"Latitude = {data_stream.TPV['lat']}")
            logger.info(fr"Longitude = {data_stream.TPV['lon']}")
            logger.info(fr"Altitude = {data_stream.TPV['alt']}")
            logger.info(fr"Speed = {inferred_speed}")


@handle_exception
def update_pressure():
    """ Broadcast the current accumulator pressure """
    global last_pressure_timestamp
    update = (datetime.datetime.now() - last_pressure_timestamp) > PRESSURE_PERIOD
    raw_pressure = pressure_sensor.read_pressure()
    was_connected = pressure_health.connected
    if not pressure_health.update(raw_pressure):
        if was_connected and poof_track.poofing():
            poof_track.stop()
            piglow.red(0)
            piglow.show()
        if update:
            # Nothing worth tracking or storing, but keep the displays alive
            broadcast("/pressure", float(round(float(poof_track.last_pressure))))
            broadcast("/pressure_fine", poof_track.last_pressure)
            last_pressure_timestamp = datetime.datetime.now()
        return
    pressure = poof_track.pressure_from_raw(raw_pressure)
    if update or pressure != poof_track.last_pressure:
        broadcast("/pressure", float(round(float(poof_track.last_pressure))))
        broadcast("/pressure_fine", poof_track.last_pressure)
        last_pressure_timestamp = datetime.datetime.now()
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
    elif not poof_track.poofing():
        piglow.red(0)
        piglow.show()


def cardinal_from_heading(heading) -> str:
    """Cardinal direction from heading value"""
    if heading >= 337.5 or heading < 22.5:
        return "N"
    if 22.5 <= heading < 67.5:
        return "NE"
    if 67.5 <= heading < 112.5:
        return "E"
    if 112.5 <= heading < 157.5:
        return "SE"
    if 157.5 <= heading < 202.5:
        return "S"
    if 202.5 <= heading < 247.5:
        return "SW"
    if 247.5 <= heading < 292.5:
        return "W"
    if 292.5 <= heading < 337.5:
        return "NW"


@handle_exception
def update_imu():
    """ Broadcast the current IMU state """
    updated_imu_state = IMU_state()
    heading = float(round(float(updated_imu_state["heading"]["tiltCompensatedHeading"])))
    if metrics.imu.shape[0] < 5 or (abs(heading - metrics.imu["heading"].iloc[-5:].mean()) > 2.0):
        broadcast("/imu", json.dumps(updated_imu_state))
        broadcast("/heading", heading)
        broadcast("/cardinal", cardinal_from_heading(heading))
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
            broadcast("/cardinal", cardinal_from_heading(float(metrics.imu["heading"].iloc[-1])))
        broadcast("/pressure", float(round(float(poof_track.last_pressure))))
        #if metrics.disk.shape[0] > 0:
        #    broadcast("/free_disk", float(metrics.disk["free"].iloc[-1]))
        broadcast("/poof_count", float(poof_track.poof_count))
        #broadcast("/poof_seconds", float(poof_track.poof_time))
        #broadcast("/engine", float(oil_pressure_sensor.sample()))
        #broadcast("/moving", float(oil_pressure_sensor.active()))


@handle_exception
def update_oil_pressure():
    """Check on oil_pressure"""
    new_value = oil_pressure_sensor.sample()
    if oil_pressure_sensor.should_broadcast(new_value):
        broadcast("/engine", float(new_value))


@handle_exception
def update_speedometer():
    """Check on speedometer"""
    new_value = speedometer_sensor.active()
    if speedometer_sensor.should_broadcast(new_value):
        if new_value:
            print("moving")
        else:
            print("stopped")
        broadcast("/moving", float(new_value))


async def main_loop():
    """Main processing loop for monitors"""
    watchdog_led = False
    hour = -1
    while True:
        try:
            metrics.persist()
            update_pressure()
            #update_oil_pressure()
            #update_speedometer()
            update_imu()
            #update_disk_usage()
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
            await asyncio.sleep(0.05)
        except Exception as exception:
            logger.error(exception)


@handle_exception
def record_water(address, *args):
    """Record the water bath state published by rhb-water-heater

    This monitor is the rig's data logger, so it keeps a history of what the
    water heater reports.  It never re-broadcasts any of it -- rhb-water-heater
    sends to every listener directly, including the body display on 10002.

    One cycle there sends /temperature, /water_heater and then /water_pressure,
    so the values are held and the row is written on the last of them.  A lost
    packet just carries the previous cycle's value into the row.
    """
    value = float(args[0])
    if address != "/water_pressure":
        water_state[address] = value
        return
    metrics.water = pd.concat(
        [
            metrics.water,
            pd.DataFrame.from_records(
                [
                    {
                        "timestamp": metrics.now_string(),
                        "temp_f": water_state["/temperature"],
                        "heater_status": water_state["/water_heater"],
                        "pressure_psi": value,
                    }
                ]
            ),
        ]
    )
    logger.info(
        f"Water temperature = {water_state['/temperature']}, "
        f"heater = {water_state['/water_heater']}, pressure = {value}"
    )


def ignore_osc(address, *args):
    """Accept and drop -- known traffic this monitor has no use for"""


def handle_unexpected(address, *args):
    """Log anything arriving that this monitor has no business receiving"""
    logger.warning(f"Unhandled OSC message {address} {args}")


async def init_main(monitor_ip):
    """Coordinate ASYNC server and main_loop processing

    This monitor owns the accumulator pressure and publishes it; everything it
    listens for here is somebody else's data that it only records.
    """
    dispatcher = Dispatcher()
    dispatcher.map("/temperature", record_water)
    dispatcher.map("/water_heater", record_water)
    dispatcher.map("/water_pressure", record_water)
    # Static setpoints; the body display shows them, this monitor does not
    dispatcher.map("/upper_temp", ignore_osc)
    dispatcher.map("/lower_temp", ignore_osc)
    dispatcher.set_default_handler(handle_unexpected)
    server = AsyncIOOSCUDPServer((monitor_ip, 8888), dispatcher, asyncio.get_event_loop())
    transport, protocol = await server.create_serve_endpoint()

    await main_loop()

    transport.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ip", default="192.168.1.3", help="The ip of the monitor"
    )
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
        "--client_ip", default="192.168.1.4,192.168.1.5,192.168.1.8,192.168.1.9,192.168.1.10,192.168.1.11", help="The IPs of the data clients"
    )
    parser.add_argument(
        "--client_port",
        type=int,
        default=8888,
        help="The port osc clients are listening on",
    )
    args = parser.parse_args()

    osc_clients = list(map(lambda x: udp_client.UDPClient(x, args.client_port), args.client_ip.split(",")))
    osc_clients = osc_clients + [udp_client.UDPClient(args.display_ip, args.display_port)]

    asyncio.run(init_main(args.ip))
