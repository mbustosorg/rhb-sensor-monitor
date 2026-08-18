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

import logging
import statistics
from collections import deque

logger = logging.getLogger("rhb-sensor-monitor")

# A connected sensor moves smoothly: across every archived session from 2023
# through 2025 the rolling median sample to sample step stayed under 400 raw
# counts (2 psi), even through the fastest poofs.  With the sensor unplugged
# the ADC input floats and consecutive samples land anywhere in the 0 - 25 psi
# band, which put the same statistic at 2100 - 3030 counts.  1000 counts
# (5 psi) sits in the middle of that gap.
JITTER_WINDOW = 40
JITTER_COUNTS = 1000

# Nothing plausible from the transducer gets anywhere near the +/- 2.048V rails
# (60 psi is 10000 counts), so a pegged reading is a wiring fault as well.
RAIL_COUNTS = 30000

# Roughly one second of junk to disconnect, two seconds of clean readings to
# come back.  Recovery is at least a full window so the statistic is computed
# entirely from post reconnection samples.
CONFIRM_SAMPLES = 20
RECOVER_SAMPLES = 40


class PressureHealth:
    """ Decide whether the pressure sensor is actually connected """

    def __init__(
        self,
        jitter_window=JITTER_WINDOW,
        jitter_counts=JITTER_COUNTS,
        rail_counts=RAIL_COUNTS,
        confirm_samples=CONFIRM_SAMPLES,
        recover_samples=RECOVER_SAMPLES,
    ):
        self.jitter_counts = jitter_counts
        self.rail_counts = rail_counts
        self.confirm_samples = confirm_samples
        self.recover_samples = recover_samples
        self.samples = deque(maxlen=jitter_window)
        self.connected = True
        self.bad_count = 0
        self.good_count = 0
        self.jitter = 0.0
        self.reason = ""

    def jitter_counts_now(self) -> float:
        """ Rolling median of the sample to sample step, in raw counts """
        if len(self.samples) < self.samples.maxlen:
            return 0.0
        values = list(self.samples)
        steps = [abs(second - first) for second, first in zip(values[1:], values)]
        return float(statistics.median(steps))

    def spurious(self, raw_pressure) -> bool:
        """ Does this reading look like a disconnected sensor? """
        if raw_pressure is None:
            self.samples.clear()
            self.reason = "no reading from the ADC"
            return True
        if abs(raw_pressure) >= self.rail_counts:
            self.samples.clear()
            self.reason = f"reading pegged at {raw_pressure} counts"
            return True
        self.samples.append(raw_pressure)
        self.jitter = self.jitter_counts_now()
        if self.jitter >= self.jitter_counts:
            self.reason = f"sample to sample noise of {self.jitter:.0f} counts"
            return True
        return False

    def update(self, raw_pressure) -> bool:
        """ Feed 'raw_pressure' in and report whether the sensor is connected """
        if self.spurious(raw_pressure):
            self.bad_count += 1
            self.good_count = 0
        else:
            self.good_count += 1
            self.bad_count = 0
        if self.connected and self.bad_count >= self.confirm_samples:
            self.connected = False
            logger.warning(f"Pressure sensor disconnected --> {self.reason}")
        elif not self.connected and self.good_count >= self.recover_samples:
            self.connected = True
            logger.warning("Pressure sensor reconnected")
        return self.connected
