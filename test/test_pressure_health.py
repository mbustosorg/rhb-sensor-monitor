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

import random

import rhb_sensor_monitor.pressure_health as ph

IDLE_COUNTS = -1800
POOF_COUNTS = 9000


def idle(count, seed=1):
    """ Readings from a connected sensor sitting at rest """
    generator = random.Random(seed)
    return [IDLE_COUNTS + generator.randint(-20, 20) for _ in range(count)]


def poof(seed=2):
    """ Readings from a connected sensor through a poof and back """
    generator = random.Random(seed)
    up = list(range(IDLE_COUNTS, POOF_COUNTS, 540))
    down = list(range(POOF_COUNTS, IDLE_COUNTS, -540))
    return [level + generator.randint(-20, 20) for level in up + down]


def floating(count, seed=3):
    """ Readings from an unplugged sensor, wandering across 0 - 25 psi """
    generator = random.Random(seed)
    return [generator.randint(-2000, 3000) for _ in range(count)]


def replay(health, readings):
    """ Feed 'readings' in and report the final connection state """
    for reading in readings:
        health.update(reading)
    return health.connected


def test_connected_at_rest():
    """ A quiet sensor stays connected """
    assert replay(ph.PressureHealth(), idle(500))


def test_connected_through_poofs():
    """ Real poofs are not mistaken for a disconnected sensor """
    health = ph.PressureHealth()
    readings = idle(100)
    for _ in range(10):
        readings += poof() + idle(40)
    assert replay(health, readings)


def test_floating_input_detected():
    """ An unplugged sensor is caught """
    health = ph.PressureHealth()
    assert not replay(health, idle(100) + floating(100))
    assert "noise" in health.reason


def test_no_reading_detected():
    """ An ADC that cannot be read counts as disconnected """
    health = ph.PressureHealth()
    assert not replay(health, idle(100) + [None] * ph.CONFIRM_SAMPLES)
    assert "ADC" in health.reason


def test_pegged_reading_detected():
    """ A reading pinned at the rail counts as disconnected """
    health = ph.PressureHealth()
    assert not replay(health, idle(100) + [32000] * ph.CONFIRM_SAMPLES)
    assert "pegged" in health.reason


def test_brief_glitch_ignored():
    """ A couple of bad readings are not enough to disconnect """
    health = ph.PressureHealth()
    assert replay(health, idle(100) + [None, None] + idle(100, seed=4))


def test_reconnect():
    """ The sensor comes back once the readings settle down """
    health = ph.PressureHealth()
    assert not replay(health, idle(100) + floating(200))
    assert replay(health, idle(200, seed=5))
