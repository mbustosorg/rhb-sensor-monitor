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

import pandas as pd
from collections import deque

PRESSURE_QUEUE_LEN = 10000
INSTANT_PRESSURE_QUEUE_LEN = 20

logger = logging.getLogger(__file__)


class PoofTrack:
    def __init__(self):
        self.poof_start = None
        self.poof_count = 0
        self.poof_time = 0.0
        self.pressure_queue = deque(maxlen=PRESSURE_QUEUE_LEN)
        self.instant_pressure_queue = deque(maxlen=INSTANT_PRESSURE_QUEUE_LEN)
        self.last_pressure = 0.0
        self.base_pressure = 0

    @staticmethod
    def pressure_from_raw(raw_pressure) -> float:
        """Compute from raw"""
        return max(float(raw_pressure) * 10.0 / 2000.0 + 10, 0.0)

    def add_observation(self, pressure):
        """ Add 'pressure' observation """
        self.last_pressure = pressure
        self.pressure_queue.appendleft(pressure)
        self.instant_pressure_queue.appendleft(pressure)
        if len(self.pressure_queue) >= PRESSURE_QUEUE_LEN:
            self.pressure_queue.pop()
        if len(self.instant_pressure_queue) >= INSTANT_PRESSURE_QUEUE_LEN:
            self.instant_pressure_queue.pop()
        if self.base_pressure == 0 or pressure != self.base_pressure:
            if not self.poofing():
                self.base_pressure = pd.Series(self.pressure_queue).median()
        if (self.base_pressure - pd.Series(self.instant_pressure_queue).median()) > 3:
            if not self.poofing():
                self.start()
        elif self.poofing():
            self.stop()

    def poofing(self):
        """ Are we poofing? """
        return self.poof_start is not None

    def start(self):
        """ Poof start detected """
        self.poof_start = datetime.datetime.now()
        self.poof_count += 1
        logger.info(f"Start poof {self.poof_count}")

    def stop(self):
        """ Poof stop detected """
        if self.poof_start is not None:
            self.poof_time = (
                self.poof_time
                + (datetime.datetime.now() - self.poof_start).total_seconds()
            )
            self.poof_start = None
            logger.info(f"Stop poof {self.poof_count}")
