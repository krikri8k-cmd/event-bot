#!/usr/bin/env python3
import sys

print("TEST OUTPUT 1", file=sys.stdout)
print("TEST OUTPUT 2", file=sys.stderr)
sys.stdout.flush()
sys.stderr.flush()
print("TEST OUTPUT 3")
