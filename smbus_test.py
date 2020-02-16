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

def read_adc():
        # ADS1115 address, 0x48(72)
        # Read data back from 0x00(00), 2 bytes
        # raw_adc MSB, raw_adc LSB
        data = bus.read_i2c_block_data(0x48, 0x00, 2)
        
        # Convert the data
        raw_adc = data[0] * 256 + data[1]
        
        if raw_adc > 32767:
	        raw_adc -= 65535
                
        # Output data to screen
        print(raw_adc)
        return raw_adc

read_adc()
