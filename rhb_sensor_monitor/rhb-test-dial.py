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
import logging
import time
import json
from time import sleep

from pythonosc import udp_client
from pythonosc import osc_bundle_builder
from pythonosc import osc_message_builder

FORMAT = "%(asctime)-15s %(message)s"
logging.basicConfig(format=FORMAT)
logger = logging.getLogger("IMU")
logger.setLevel(logging.INFO)

last_message_time = int(time.time())
last_pressure = 0


def send_pressure_update(pressure):
    """ Broadcast the current accumulator pressure """
    global last_pressure

    if abs(pressure - last_pressure) > 300:
        last_pressure = pressure
        msg = osc_message_builder.OscMessageBuilder(address="/pressure")
        msg.add_arg(pressure)
        built = msg.build()
        pressure_client.send(built)
        mobile_client.send(built)
        logger.info(f"Pressure = {pressure}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pressure_ip", default="10.0.1.58", help="The ip of the pressure osc server"
    )
    parser.add_argument(
        "--pressure_port",
        type=int,
        default=10003,
        help="The port the pressure osc server is listening on",
    )
    parser.add_argument(
        "--mobile_ip", default="10.0.1.17", help="The ip of the mobile osc display"
    )
    parser.add_argument(
        "--mobile_port",
        type=int,
        default=10004,
        help="The port the mobile osc display is listening on",
    )
    args = parser.parse_args()

    pressure_client = udp_client.UDPClient(args.pressure_ip, args.pressure_port)
    mobile_client = udp_client.UDPClient(args.mobile_ip, args.mobile_port)

    current_pressure = -1000
    while True:
        current_time = int(time.time())
        if last_message_time < current_time:
            current_pressure += 1000
            send_pressure_update(current_pressure)
            last_message_time = current_time
