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

import datetime
import logging
import time

import pandas as pd
from collections import deque

PRESSURE_QUEUE_LEN = 10000
INSTANT_PRESSURE_QUEUE_LEN = 40

logger = logging.getLogger("rhb-sensor-monitor")


class PoofCounter:
    """Poof count and cumulative poof time, from whatever says a poof started"""

    def __init__(self):
        self.poof_start = None
        self.poof_count = 0
        self.poof_time = 0.0

    def poofing(self):
        """ Are we poofing? """
        return self.poof_start is not None

    def start(self):
        """ Poof start detected """
        # Monotonic, so a clock set from GPS mid-poof cannot make one hours long
        self.poof_start = time.monotonic()
        self.poof_count += 1

    def stop(self):
        """ Poof stop detected """
        if self.poof_start is not None:
            self.poof_time = (
                self.poof_time
                + (time.monotonic() - self.poof_start)
            )
            self.poof_start = None


class ButtonPoofTrack(PoofCounter):
    """Poofs as rhb-poof-controller's button reports them on /poof

    The controller sends 1.0 on press and 0.0 on release, and sends the
    release three times over in case one is lost.  Only a change of state
    counts, so a repeated value is harmless.
    """

    def update(self, value) -> bool:
        """Apply one /poof value; True when it started or ended a poof"""
        if float(value) >= 0.5:
            if self.poofing():
                return False
            self.start()
        else:
            if not self.poofing():
                return False
            self.stop()
        return True


class PoofTrack(PoofCounter):
    """Poofs inferred from the accumulator pressure drop

    Superseded by ButtonPoofTrack as the source of /poof_count, and kept
    running so the two can be compared.
    """

    def __init__(self):
        super().__init__()
        self.pressure_queue = deque(maxlen=PRESSURE_QUEUE_LEN)
        self.instant_pressure_queue = deque(maxlen=INSTANT_PRESSURE_QUEUE_LEN)
        self.last_pressure = 0.0
        self.base_pressure = 0

    @staticmethod
    def pressure_from_raw(raw_pressure) -> float:
        """Compute from raw rounded to 0.1"""
        observation = max(float(raw_pressure) * 10.0 / 2000.0 + 10, 0.0)
        observation = float(int(observation * 10.0)) / 10.0
        return observation

    def add_observation(self, pressure):
        """ Add 'pressure' observation """
        self.last_pressure = int(pressure)
        self.pressure_queue.appendleft(self.last_pressure)
        self.instant_pressure_queue.appendleft(self.last_pressure)
        if len(self.pressure_queue) >= PRESSURE_QUEUE_LEN:
            self.pressure_queue.pop()
        if len(self.instant_pressure_queue) >= INSTANT_PRESSURE_QUEUE_LEN:
            self.instant_pressure_queue.pop()
        if not self.poofing():
            if self.base_pressure != pd.Series(self.pressure_queue).median():
                self.base_pressure = pd.Series(self.pressure_queue).median()
                logger.info(f"base_pressure set to {self.base_pressure}")
        if abs(self.last_pressure - self.base_pressure) > 3:
            if not self.poofing():
                self.start()
                logger.info(f"PoofStart --> Count: {self.poof_count}, last_pressure: {self.last_pressure}, base_pressure: {self.base_pressure}")
        elif self.poofing():
            if self.last_pressure <= self.base_pressure:
                self.stop()
                logger.info(f"PoofStop --> Count: {self.poof_count}, last_pressure: {self.last_pressure}, base_pressure: {self.base_pressure}")

