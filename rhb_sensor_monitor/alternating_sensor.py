"""State sensor that can be alternating with a timeout"""
import datetime

import RPi.GPIO as GPIO


class AlternatingSensor:
    
    def __init__(self, pin: int, name: str, timeout_ms: int):
        """Initialize the sensor"""
        self.pin = pin
        self.name = name
        self.timeout = timeout_ms
        self.last_state = False
        self.last_change_time = None
        self.last_broadcast = False
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def sample(self) -> bool:
        """Sample the sensor to see if we are ticking"""
        current_state = not GPIO.input(self.pin)
        if current_state is not self.last_state:
            self.last_state = current_state
            self.last_change_time = datetime.datetime.now()
        return current_state

    def active(self) -> bool:
        """Is the sensor active?"""
        self.sample()
        if self.last_change_time:
            diff = (datetime.datetime.now() - self.last_change_time)
            return diff.total_seconds() * 1000 < self.timeout
        return False

    def should_broadcast(self, new_value) -> bool:
        """Should we broadcast the new value?"""
        if new_value is not self.last_broadcast:
            self.last_broadcast = new_value
            return True
        return False