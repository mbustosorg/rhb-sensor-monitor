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


import rhb_sensor_monitor.poof_track as pt


def test_not_poofing():
    """ Ensure we are not poofing by default """
    tracker = pt.PoofTrack()
    for i in range(100):
        tracker.add_observation(1000)
    assert not tracker.poofing()


def test_one_poof():
    """ Poof once """
    tracker = pt.PoofTrack()
    for i in range(100):
        tracker.add_observation(1000)
    for i in reversed(range(10)):
        tracker.add_observation(i)
    assert tracker.poofing()
    assert tracker.poof_count == 1


def test_two_poofs():
    """ Poof twice """
    tracker = pt.PoofTrack()
    for i in range(100):
        tracker.add_observation(1000)
    for i in reversed(range(10)):
        tracker.add_observation(i)
    for i in range(10):
        tracker.add_observation(1000)
    for i in reversed(range(10)):
        tracker.add_observation(i)
    assert tracker.poofing()
    assert tracker.poof_count == 2