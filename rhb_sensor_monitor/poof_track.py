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
import pandas as pd
from collections import deque

PRESSURE_QUEUE_LEN = 10000


class PoofTrack:

    def __init__(self):
        self.poof_start = None
        self.poof_count = 0
        self.poof_time = 0.0
        self.pressure_queue = deque(maxlen=PRESSURE_QUEUE_LEN)
        self.base_pressure = 0

    def add_observation(self, pressure):
        """ Add 'pressure' observation """
        self.pressure_queue.appendleft(pressure)
        if len(self.pressure_queue) >= PRESSURE_QUEUE_LEN:
            self.pressure_queue.pop()
        if self.base_pressure == 0 or pressure != self.base_pressure:
            self.base_pressure = pd.Series(self.pressure_queue).mode()[0]
        if abs(pressure - self.base_pressure) > 300:
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

    def stop(self):
        """ Poof stop detected """
        self.poof_time = self.poof_time + (datetime.datetime.now() - self.poof_start).total_seconds()
        self.poof_start = None
