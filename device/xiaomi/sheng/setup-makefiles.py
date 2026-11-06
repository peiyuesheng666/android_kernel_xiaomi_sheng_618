#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys

script = Path(__file__).with_name('extract-files.py')
os.execv(sys.executable, [sys.executable, str(script), '--regenerate_makefiles', *sys.argv[1:]])
