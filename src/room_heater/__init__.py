__vesion__ = "0.0.1"

import sys

from .heater import SmartHeater

def main():
    if len(sys.argv) == 2:
        if sys.argv[1] == '--about':
            print(__doc__)
        elif sys.argv[1] == '--version':
            print("Smart Room Heater 0.0.1")
        elif sys.argv[1] == '--help':
            print("Smart Room Heater")
            print("Usage: python -m room_heater [option]")
            print("  --about  : program information")
            print("  --version: program version")
            print("  --help   : help")
            print("  (no option) : run room heater")
    else:
        heater = SmartHeater()
        heater.run()

__all__ = ["SmartHeater", "main", "__version__"]