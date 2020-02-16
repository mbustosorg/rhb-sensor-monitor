import smbus
import time

# Get I2C bus
bus = smbus.SMBus(1)

# ADS1115 address, 0x48(72)
# Select configuration register, 0x01(01)
#		0x8483(33923)	AINP = AIN0 and AINN = AIN1, +/- 2.048V
#				Continuous conversion mode, 128SPS
data = [0x84,0x83]
bus.write_i2c_block_data(0x48, 0x01, data)
time.sleep(0.5)

def read_pressure():
    global last_data
    
    try:
        raw_adc = 0
        data = bus.read_i2c_block_data(0x48, 0x00, 2)
        raw_adc = data[0] * 256 + data[1]
        if raw_adc > 32767:
            raw_adc -= 65535
    except Exception as e:
        return raw_adc
    return raw_adc

