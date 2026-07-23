#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: simplemodel.py
Author: Fitz Kurtz
"""

from pythonfmu import Fmi2Slave

class SimpleModel(Fmi2Slave):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._output = 0.0

    def do_step(self, current_time, step_size):
        self._output = (current_time + step_size) * 2
        return True  # signals successful step