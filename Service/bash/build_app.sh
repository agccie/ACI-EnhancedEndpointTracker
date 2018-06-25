#!/bin/bash

# just a proxy to build.py ensuring correct working directory
# ensure user arguments are passed to python script
# ensure we're executing in directory where script is located
cd ${0%/*}
cd ../aci_app_store/
python ./build.py $@


