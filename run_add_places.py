#!/usr/bin/env python3
"""Запуск добавления мест с правильной кодировкой"""

import os
import sys
from pathlib import Path

# Устанавливаем UTF-8 для stdout
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")

# Запускаем скрипт
os.chdir(Path(__file__).parent)
os.system("python scripts/add_places_from_simple_file.py food_places_example.txt")
