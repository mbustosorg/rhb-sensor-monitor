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

import smbus
import time

bus = smbus.SMBus(1)

# ADS1115 address, 0x48(72)
# Select configuration register, 0x01(01)
#		0x8483(33923)	AINP = AIN0 and AINN = AIN1, +/- 2.048V
#				Continuous conversion mode, 128SPS

data = [0x84,0x83]
bus.write_i2c_block_data(0x48, 0x01, data)
time.sleep(0.5)

def read_pressure():
    """ Read pressure sensor from ADC """
    try:
        raw_adc = 0
        data = bus.read_i2c_block_data(0x48, 0x00, 2)
        raw_adc = data[0] * 256 + data[1]
        if raw_adc > 32767:
            raw_adc -= 65535
    except Exception as e:
        print("x")
        return raw_adc
    return raw_adc

