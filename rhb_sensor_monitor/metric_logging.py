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
import time
import pandas as pd


class MetricLogging:
    """ Rolling sensor histories, and when to persist and rebroadcast them

    Intervals are timed on time.monotonic(), never on the wall clock.  This Pi
    has no RTC: it comes up with the clock about seven hours fast and the first
    GPS fix sets it back.  Timed on the wall clock, the elapsed time since the
    last persist went negative at that step and stayed under the period for
    seven hours, so nothing was persisted, rebroadcast or sent to the base
    station until dawn.  The wall clock is still what stamps rows and names
    files, since that is the time the logs have to line up against.
    """

    def __init__(self, persist_period, broadcast_period, location):
        self.location = location
        self.last_broadcast = time.monotonic()
        self.last_radio_broadcast = time.monotonic()
        self.last_persist = time.monotonic()
        self.last_persist_timestamp = None
        self.pressure = None
        self.position = None
        self.imu = None
        self.water = None
        self.disk = None
        self.persist_period = persist_period
        self.broadcast_period = broadcast_period
        self.initialize()

    @staticmethod
    def now_string():
        """ Formatted date string """
        return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")

    def initialize(self):
        """ Re-initialize history records """
        self.pressure = pd.DataFrame(columns=["timestamp", "level"])
        self.position = pd.DataFrame(columns=["timestamp", "lat", "lon", "alt"])
        self.imu = pd.DataFrame(columns=["timestamp", "heading", "speed"])
        self.water = pd.DataFrame(columns=["timestamp", "temp_f", "heater_status", "pressure_psi"])
        self.disk = pd.DataFrame(columns=["timestamp", "free"])

    def persist(self):
        """ Store off histories periodically """
        if time.monotonic() - self.last_persist > self.persist_period.total_seconds():
            self.last_persist = time.monotonic()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H_%M")
            self.position.to_csv(
                os.path.join(self.location, "positions_" + timestamp + ".csv"),
                index=False,
            )
            self.pressure.to_csv(
                os.path.join(self.location, "pressure_" + timestamp + ".csv"),
                index=False,
            )
            self.imu.to_csv(
                os.path.join(self.location, "heading_" + timestamp + ".csv"),
                index=False,
            )
            self.water.to_csv(
                os.path.join(self.location, "water_" + timestamp + ".csv"), index=False
            )
            self.disk.to_csv(
                os.path.join(self.location, "disk_" + timestamp + ".csv"), index=False
            )
            if self.last_persist_timestamp != timestamp:
                self.last_persist_timestamp = timestamp
                self.initialize()

    def time_to_broadcast(self):
        """ Should we broadcast an update? """
        if time.monotonic() - self.last_broadcast > self.broadcast_period.total_seconds():
            self.last_broadcast = time.monotonic()
            return True
        return False

    def time_to_broadcast_by_radio(self):
        """ Should we broadcast an update? """
        if time.monotonic() - self.last_radio_broadcast > self.broadcast_period.total_seconds() * 10:
            self.last_radio_broadcast = time.monotonic()
            return True
        return False
