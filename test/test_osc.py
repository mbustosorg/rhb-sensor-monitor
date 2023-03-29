"""
    Copyright (C) 2022 Mauricio Bustos (m@bustos.org)
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

import time

from pythonosc import osc_message_builder
from pythonosc import udp_client

endpoints = [
    "/position/lat",
    "/position/lon",
    "/heading",
    "/temperature",
    "/temperature_cpu",
    "/pressure",
    "/poof_count",
    "/tick/dial",
    "/dial_temperature_cpu"
]


clients = [
    udp_client.UDPClient("127.0.0.1", 10002),  # display
    udp_client.UDPClient("192.168.1.4", 8888),  # dial
    udp_client.UDPClient("192.168.1.5", 8888),  # mobile
]


def broadcast(endpoint, value):
    """Send value to all clients"""
    msg = osc_message_builder.OscMessageBuilder(address=endpoint)
    msg.add_arg(value)
    built = msg.build()
    for client in clients:
        client.send(built)


def test_heading():
    """Test heading updates"""
    for i in range(0, 360, 2):
        broadcast("/heading", float(i))
        time.sleep(0.05)


def test_pressure():
    """Test heading updates"""
    for i in range(1300, 2200, 5):
        broadcast("/pressure", float(i))
        time.sleep(0.05)


def test_temperature():
    """Test heading updates"""
    for i in range(40, 90):
        broadcast("/temperature", float(i))
        time.sleep(0.1)
