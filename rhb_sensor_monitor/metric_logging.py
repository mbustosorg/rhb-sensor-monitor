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

import csv
import datetime
import logging
import os
import time
import pandas as pd

logger = logging.getLogger("rhb-sensor-monitor")

# Attribute holding the recent rows -> (file prefix, columns)
STREAMS = {
    "pressure": ("pressure", ["timestamp", "level"]),
    "position": ("positions", ["timestamp", "lat", "lon", "alt", "speed"]),
    "imu": ("heading", ["timestamp", "heading"]),
    "water": ("water", ["timestamp", "temp_f", "heater_status", "pressure_psi"]),
    "disk": ("disk", ["timestamp", "free"]),
    "poofs": ("poofs", ["timestamp", "source", "event", "count", "poof_time"]),
}

# How often written rows are forced onto the stick, bounding what a power
# cut can take to this many seconds
SYNC_PERIOD = 5.0


class MetricLogging:
    """ Sensor histories, streamed to CSV, and when to rebroadcast them

    Every row is written to its file as it is recorded, and the files are
    fsynced every SYNC_PERIOD seconds.  This car loses power without warning;
    the histories used to be held in memory and written once a period, so a
    power cut took up to fifteen minutes of every one of them.

    Files roll every persist_period, as <prefix>_YYYYMMDD_HH_MM.csv named for
    the wall clock when the file's first row arrived.  An existing file is
    appended to rather than overwritten: once GPS sets the clock back, a
    window's name can repeat one already on the stick.

    The rows of the current window are also kept in memory (self.pressure,
    self.position, ...), since the monitor decides what to record next from
    them.  They start empty each window, so each file opens with a fresh row.

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
        self.last_sync = time.monotonic()
        self.files = {}
        self.failing = set()
        self.pressure = None
        self.position = None
        self.imu = None
        self.water = None
        self.disk = None
        self.poofs = None
        self.persist_period = persist_period
        self.broadcast_period = broadcast_period
        self.initialize()

    @staticmethod
    def now_string():
        """ Formatted date string """
        return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")

    def initialize(self):
        """ Start a fresh window of recent rows """
        for kind, (_, columns) in STREAMS.items():
            setattr(self, kind, pd.DataFrame(columns=columns))

    def append(self, kind, **values):
        """ Record one row of `kind', stamped now, in memory and on disk """
        row = {"timestamp": self.now_string(), **values}
        setattr(self, kind, pd.concat([getattr(self, kind), pd.DataFrame.from_records([row])]))
        self._write(kind, row)

    def _write(self, kind, row):
        """ Append `row' to the current file for `kind'

        Never raises: a missing or full stick must not stop the monitor
        publishing.  The failure is logged once, and the file reopened on the
        next row.
        """
        prefix, columns = STREAMS[kind]
        try:
            if kind not in self.files:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H_%M")
                path = os.path.join(self.location, f"{prefix}_{timestamp}.csv")
                handle = open(path, "a", newline="")
                writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
                if handle.tell() == 0:
                    writer.writeheader()
                self.files[kind] = (handle, writer)
            handle, writer = self.files[kind]
            writer.writerow(row)
            handle.flush()
            if kind in self.failing:
                self.failing.discard(kind)
                logger.info(f"Writing {prefix} history again")
        except Exception as exception:
            self._close(kind)
            if kind not in self.failing:
                self.failing.add(kind)
                logger.error(f"Could not write {prefix} history: {exception}")

    def _close(self, kind):
        """ Sync and close the file for `kind', if one is open """
        handle, _ = self.files.pop(kind, (None, None))
        if handle is not None:
            try:
                handle.flush()
                os.fsync(handle.fileno())
                handle.close()
            except Exception as exception:
                logger.error(f"Could not close {handle.name}: {exception}")

    def sync(self):
        """ Force everything written so far onto the disk """
        for kind, (handle, _) in list(self.files.items()):
            try:
                os.fsync(handle.fileno())
            except Exception as exception:
                logger.error(f"Could not sync {handle.name}: {exception}")
                self._close(kind)

    def persist(self):
        """ Sync streamed rows periodically, and roll to new files each period """
        if time.monotonic() - self.last_sync > SYNC_PERIOD:
            self.last_sync = time.monotonic()
            self.sync()
        if time.monotonic() - self.last_persist > self.persist_period.total_seconds():
            self.last_persist = time.monotonic()
            for kind in list(self.files):
                self._close(kind)
            self.initialize()

    def close(self):
        """ Sync and close every file """
        for kind in list(self.files):
            self._close(kind)

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
