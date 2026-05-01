#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File: modelica-fmu.py
Author: Kathryn Hinkelman
Date: 2025-08-18
Description: Creates and loads an FMU from a Modelica library, simulates and plots  
"""

# Import packages
import os
import json
import matplotlib.pyplot as plt
from fmpy import simulate_fmu
import buildingspy.fmi as f

# Get the FMI
#fmu_name=os.path.join("Data", "WindTurbine.fmu")
fmu_name=os.path.join("Data", "Buildings_Fluid_FMI_Validation_HeaterFan.fmu")
d=f.get_dependencies(fmu_name)
# print(json.dumps(d, indent=2, separators=(',', ': '), sort_keys=True))

# Load and simulate the FMU
output_variables = ['hea.com.vol.T', 'sou.T_in', 'sin.T_in']
stopTime = 3600*24
res = simulate_fmu(fmu_name, start_time=0, stop_time=stopTime, solver='CVode', output=output_variables)

# Set variables to plot  
time = res['time']
heater = res['hea.com.vol.T'] 
source = res['sou.T_in']
sink = res['sin.T_in']

# Plot results in one plot
plt.figure(figsize=(10, 6))
plt.plot(time, heater, label='Heater Temperature', linewidth=2)
plt.plot(time, source, label='Source Temperature', linewidth=2)
plt.plot(time, sink, label='Sink Temperature', linewidth=2)
plt.xlabel('Time (s)')
plt.ylabel('Temperature (K)')
plt.legend()
plt.title('Buildings Fluid FMI Validation - HeaterFan Model')
plt.grid(True, alpha=0.3)
plt.show()

print(f"\nSimulation completed!")
print(f"Time range: {time.min():.1f} - {time.max():.1f} seconds")
print(f"Heater temp range: {heater.min():.1f} - {heater.max():.1f} K")
print(f"Source temp range: {source.min():.1f} - {source.max():.1f} K")
print(f"Sink temp range: {sink.min():.1f} - {sink.max():.1f} K")
