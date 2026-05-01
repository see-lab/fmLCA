#!/bin/zsh

## this is a zshell script to automatically fix the FMU made with pythonfmu so that it will run however we like.
## to work in bash, just change the shebang to #!/bin/bash

# initial args
input=$1
cleanup=$2

# create a zip copy
output=${input%.fmu}.zip
cp "$input" "$output"

# unzip the zip and change the xml file
folder=${output%.zip}_contents
mkdir -p "$folder"
unzip "$output" -d "$folder"
file="$folder/modelDescription.xml"
sed -i 's/needsExecutionTool="true"/needsExecutionTool="false"/g' "$file"

# rezip the file and name it to fixed_fmu
final_fmu=${output%.zip}_fixed.fmu 
final_fmu_abs=$(realpath --relative-to="$folder" "$final_fmu")
cd "$folder" || exit
zip -r "$final_fmu_abs" *
cd -

echo "Fixed FMU created: $final_fmu"

# delete the interstitial files (the folder)
if [[ -n "$cleanup" ]]; then
  rm -rf "$folder" "$output"
  echo "Cleaned: $folder and $output"
fi


