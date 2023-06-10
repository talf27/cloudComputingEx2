#!/bin/bash

data="$1"
iterations="$2"

decoded_data=$(echo "$data" | base64 --decode)
iterations_int=$(($iterations))

output=$decoded_data
for ((i=0; i<iterations_int; i++)); do
    output=$(echo -n "$output" | sha512sum | awk '{print $1}')
done

echo "$output"