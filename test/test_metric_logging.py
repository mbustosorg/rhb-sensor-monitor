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


def rows(path):
    return path.read_text().splitlines()


def test_rows_stream_to_disk(tmp_path, monkeypatch):
    """ A row is on disk as soon as it is recorded, not at the end of the window """
    clocks = Clocks(datetime.datetime(2026, 8, 30, 22, 45))
    metrics = logging_at(tmp_path, clocks, monkeypatch)
    metrics.append("pressure", level=12.5)
    metrics.append("poofs", source="button", event="start", count=1, poof_time=0.0)
    assert rows(tmp_path / "pressure_20260830_22_45.csv") == ["timestamp,level", "2026-08-30T22:45:00.000000,12.5"]
    assert rows(tmp_path / "poofs_20260830_22_45.csv")[1].endswith(",button,start,1,0.0")
    assert not (tmp_path / "positions_20260830_22_45.csv").exists()


def test_persist_rolls_to_a_new_file(tmp_path, monkeypatch):
    clocks = Clocks(datetime.datetime(2026, 8, 30, 22, 45))
    metrics = logging_at(tmp_path, clocks, monkeypatch)
    metrics.append("pressure", level=12.0)
    clocks.advance(15 * 60 + 1)
    metrics.persist()
    assert metrics.pressure.empty
    metrics.append("pressure", level=13.0)
    assert len(rows(tmp_path / "pressure_20260830_22_45.csv")) == 2
    assert len(rows(tmp_path / "pressure_20260830_23_00.csv")) == 2


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
    metrics.append("position", lat=37.0, lon=-122.0, alt=10.0, speed=0.0)
    assert (tmp_path / "positions_20260830_23_00.csv").exists()


def test_a_repeated_name_appends(tmp_path, monkeypatch):
    """ Once the clock is set back a window's name can repeat; keep both """
    clocks = Clocks(datetime.datetime(2026, 8, 30, 22, 45))
    metrics = logging_at(tmp_path, clocks, monkeypatch)
    metrics.append("water", temp_f=90.0, heater_status=1.0, pressure_psi=20.0)
    clocks.advance(15 * 60 + 1)
    metrics.persist()
    clocks.wall = datetime.datetime(2026, 8, 30, 22, 45)
    metrics.append("water", temp_f=91.0, heater_status=0.0, pressure_psi=20.0)
    assert rows(tmp_path / "water_20260830_22_45.csv") == [
        "timestamp,temp_f,heater_status,pressure_psi",
        "2026-08-30T22:45:00.000000,90.0,1.0,20.0",
        "2026-08-30T22:45:00.000000,91.0,0.0,20.0",
    ]


def test_a_missing_stick_does_not_raise(tmp_path, monkeypatch):
    clocks = Clocks(datetime.datetime(2026, 8, 30, 22, 45))
    metrics = logging_at(tmp_path / "gone", clocks, monkeypatch)
    metrics.append("pressure", level=12.0)
    clocks.advance(6)
    metrics.persist()
    assert metrics.pressure["level"].iloc[-1] == 12.0
    (tmp_path / "gone").mkdir()
    metrics.append("pressure", level=13.0)
    assert len(rows(tmp_path / "gone" / "pressure_20260830_22_45.csv")) == 2


def test_broadcast_survives_the_clock_being_set_back(tmp_path, monkeypatch):
    clocks = Clocks(datetime.datetime(2026, 8, 31, 5, 45))
    metrics = logging_at(tmp_path, clocks, monkeypatch)
    clocks.wall = datetime.datetime(2026, 8, 30, 22, 45)
    clocks.advance(6)
    assert metrics.time_to_broadcast()
    assert not metrics.time_to_broadcast()
    clocks.advance(45)
    assert metrics.time_to_broadcast_by_radio()


def test_memory_keeps_only_recent_rows(tmp_path, monkeypatch):
    """ An hour of poofing is every reading; only the file keeps them all """
    clocks = Clocks(datetime.datetime(2026, 8, 30, 22, 45))
    metrics = logging_at(tmp_path, clocks, monkeypatch)
    for level in range(ml.RECENT_ROWS + 50):
        metrics.append("pressure", level=level)
    assert len(metrics.pressure) == ml.RECENT_ROWS
    assert metrics.pressure["level"].iloc[-1] == ml.RECENT_ROWS + 49
    assert len(rows(tmp_path / "pressure_20260830_22_45.csv")) == ml.RECENT_ROWS + 51
