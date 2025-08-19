#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: OneFMU.py
Author: Kathryn Hinkelman
Date: 2025-08-18
Description: Creates and loads an FMU from a Modelica library, simulates and plots  
"""

# Import packages
import os
import json
import matplotlib.pyplot as plt
from pyfmi import load_fmu
import buildingspy.fmi as f

# Get the FMI
#fmu_name=os.path.join("Data", "WindTurbine.fmu")
fmu_name=os.path.join("Data", "Buildings_Fluid_FMI_Validation_HeaterFan.fmu")
d=f.get_dependencies(fmu_name)
print(json.dumps(d, indent=2, separators=(',', ': '), sort_keys=True))

# Load and simulate the FMU
model = load_fmu(fmu_name)
opts = model.simulate_options()
opts['solver'] = 'CVode'
res = model.simulate(start_time=0, final_time=1, options=opts)

# Set variables to plot
time = res['time']
heater = res['hea.com.vol.T']
source = res['sou.T_in']
sink = res['sin.T_in']

# Plot results in one plot
plt.figure()
plt.plot(time, heater, label='Heater Temperature')
plt.plot(time, source, label='Source Temperature')
plt.plot(time, sink, label='Sink Temperature')
plt.xlabel('Time (s)')
plt.ylabel('Temperature (K)')
plt.legend()
plt.show()
