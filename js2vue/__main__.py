"""
Allows execution via `python -m js2vue.translate` or `python -m js2vue translate`.
"""

import sys
from js2vue.translate import main

if __name__ == "__main__":
    sys.exit(main())
