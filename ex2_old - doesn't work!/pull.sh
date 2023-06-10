#!/bin/bash

completed_work_str=$1
top=$2

# Split the list string into an array
IFS=' ' read -ra completed_work_list <<< "$completed_work_str"

# Get the last 'top' elements of the array
start_index=$(( ${#completed_work_list[@]} - top ))
last_elements=("${completed_work_list[@]:$start_index}")

# Access and print the last 'top' elements
for item in "${last_elements[@]}"; do
    echo $item
done
