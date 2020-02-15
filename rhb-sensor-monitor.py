""" Monitor IMU """

import argparse
import logging
import time
from time import sleep

import board
import busio

from pythonosc import udp_client
from pythonosc import osc_bundle_builder
from pythonosc import osc_message_builder

from gps3 import gps3
from imu.berryIMU import IMU_state

gps_socket = gps3.GPSDSocket()
data_stream = gps3.DataStream()

FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger('IMU')
logger.setLevel(logging.INFO)

gps_socket.connect()
gps_socket.watch()

i2c = busio.I2C(board.SCL, board.SDA)
import adafruit_ads1x15.ads1015 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
ads = ADS.ADS1015(i2c)
chan = AnalogIn(ads, ADS.P0)

last_message_time = int(time.time())
pressure = 0.0
pressure_direction = True

def send_position_update(data_stream):
    msg = osc_message_builder.OscMessageBuilder(address="/position")
    msg.add_arg(data_stream.TPV['alt'])
    msg.add_arg(data_stream.TPV['lat'])
    msg.add_arg(data_stream.TPV['lon'])
    display_client.send(msg.build())
    logger.info(fr"Altitude = {data_stream.TPV['alt']}")
    logger.info(fr"Latitude = {data_stream.TPV['lat']}")
    logger.info(fr"Latitude = {data_stream.TPV['lon']}")

def send_pressure_update(pressure):
    msg = osc_message_builder.OscMessageBuilder(address='/pressure')
    msg.add_arg(pressure)
    pressure_client.send(msg.build())
    logger.info(f'Pressure = {pressure}')

def send_imu_update():
    return ''
    
if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--display_ip', default='127.0.0.1', help='The ip of the display osc server')
  parser.add_argument('--display_port', type=int, default=10002, help='The port the display osc server is listening on')
  parser.add_argument('--pressure_ip', default='10.0.1.58', help='The ip of the pressure osc server')
  parser.add_argument('--pressure_port', type=int, default=10003, help='The port the pressure osc server is listening on')
  args = parser.parse_args()

  display_client = udp_client.UDPClient(args.display_ip, args.display_port)
  pressure_client = udp_client.UDPClient(args.pressure_ip, args.pressure_port)
  
  while True:
      for new_data in gps_socket:
          if new_data:
              imu_state = IMU_state()
              data_stream.unpack(new_data)
              current_time = int(time.time())
              if last_message_time < current_time:
                  logger.info(f'analog value = {chan.value}, analog voltage = {chan.voltage}')
                  logger.info(imu_state)
                  last_message_time = current_time
                  send_position_update(data_stream)
                  send_pressure_update(chan.value)

            
