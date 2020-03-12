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

import os
import datetime
import pandas as pd


class MetricLogging:

    def __init__(self, persist_period, location):
        self.location = location
        self.last_persist = datetime.datetime.now()
        self.pressure = None
        self.position = None
        self.imu = None
        self.temp = None
        self.persist_period = persist_period
        self.initialize()

    @staticmethod
    def now_string():
        """ Formatted date string """
        return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')

    def initialize(self):
        """ Re-initialize history records """
        self.pressure = pd.DataFrame(columns=['timestamp', 'level'])
        self.position = pd.DataFrame(columns=['timestamp', 'lat', 'lon'])
        self.imu = pd.DataFrame(columns=['timestamp', 'heading'])
        self.temp = pd.DataFrame(columns=['timestamp', 'temp_f'])

    def persist(self):
        """ Store off histories periodically """
        if datetime.datetime.now() - self.last_persist > self.persist_period:
            timestamp = str(int(datetime.datetime.now().timestamp()))
            self.position.to_csv(os.path.join(self.location, 'positions_' + timestamp + '.csv'))
            self.pressure.to_csv(os.path.join('pressure_' + timestamp + '.csv'))
            self.imu.to_csv(os.path.join('heading_' + timestamp + '.csv'))
            self.temp.to_csv(os.path.join('temp_' + timestamp + '.csv'))
