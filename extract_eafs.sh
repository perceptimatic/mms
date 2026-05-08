#!/usr/bin/env bash

for file in perrony_data/train/*.eaf; do
    filename="$(basename $file ".eaf")"
    python3 local/dump_eaf.py "$file" "eafs/$filename.tws"
done