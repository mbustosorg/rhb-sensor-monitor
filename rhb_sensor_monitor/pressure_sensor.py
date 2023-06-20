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

import time

import smbus

bus = smbus.SMBus(1)

# ADS1115 address, 0x48(72)
# Select configuration register, 0x01(01)
# 		0x8483(33923)	AINP = AIN0 and AINN = AIN1, +/- 2.048V
# 				Continuous conversion mode, 128SPS

DATA = [0x84, 0x83]
DATA = [0x84, 0xC3]
bus.write_i2c_block_data(0x48, 0x01, DATA)
time.sleep(0.5)


def read_pressure():
    """ Read pressure sensor from ADC """
    raw_data = bus.read_i2c_block_data(0x48, 0x00, 2)
    raw_adc = raw_data[0] * 256 + raw_data[1]
    raw_adc_mod = raw_adc
    if raw_adc > 32767:
        raw_adc_mod -= 65535
    return raw_adc_mod
