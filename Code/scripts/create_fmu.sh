fmipp_create_fmu \
    --model-name PowerSink \
    --python-class PowerSink \
    --python-file PowerSink.py \
    --fmi-version 2 \
    --interface-type CoSimulation \
    --description "Power input integrator" \
    --output-dir PowerSink_fmu \
    --model-description modelDescription.xml.in