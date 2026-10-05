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

import rhb_sensor_monitor.metric_logging as ml


class Clocks:
    """ A wall clock and a monotonic clock that can be moved independently """

    def __init__(self, wall):
        self.wall = wall
        self.mono = 1000.0

    def advance(self, seconds):
        self.wall += datetime.timedelta(seconds=seconds)
        self.mono += seconds

    def install(self, monkeypatch):
        clocks = self

        class Wall(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return clocks.wall

        monkeypatch.setattr(ml.datetime, "datetime", Wall)
        monkeypatch.setattr(ml.time, "monotonic", lambda: clocks.mono)


def logging_at(tmp_path, clocks, monkeypatch):
    clocks.install(monkeypatch)
    return ml.MetricLogging(datetime.timedelta(minutes=15), datetime.timedelta(seconds=5), str(tmp_path))


def test_persist(tmp_path, monkeypatch):
    clocks = Clocks(datetime.datetime(2026, 8, 30, 22, 45))
    metrics = logging_at(tmp_path, clocks, monkeypatch)
    metrics.persist()
    assert not list(tmp_path.iterdir())
    clocks.advance(15 * 60 + 1)
    metrics.persist()
    assert (tmp_path / "pressure_20260830_23_00.csv").exists()


def test_persist_survives_the_clock_being_set_back(tmp_path, monkeypatch):
    """ 2026: the Pi woke seven hours fast and GPS set it back moments later

    On the wall clock that held the persist off until dawn.  It has to come
    fifteen minutes after start, and be named for the corrected time.
    """
    clocks = Clocks(datetime.datetime(2026, 8, 31, 5, 45))
    metrics = logging_at(tmp_path, clocks, monkeypatch)
    clocks.wall = datetime.datetime(2026, 8, 30, 22, 45)
    clocks.advance(15 * 60 + 1)
    metrics.persist()
    assert (tmp_path / "positions_20260830_23_00.csv").exists()


def test_broadcast_survives_the_clock_being_set_back(tmp_path, monkeypatch):
    clocks = Clocks(datetime.datetime(2026, 8, 31, 5, 45))
    metrics = logging_at(tmp_path, clocks, monkeypatch)
    clocks.wall = datetime.datetime(2026, 8, 30, 22, 45)
    clocks.advance(6)
    assert metrics.time_to_broadcast()
    assert not metrics.time_to_broadcast()
    clocks.advance(45)
    assert metrics.time_to_broadcast_by_radio()
