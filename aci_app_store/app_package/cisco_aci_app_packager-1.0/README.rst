Copyright (c) 2016 Cisco Systems Inc. All rights reserved.
Cisco ACI app packager script

This script will validate if the directory structure conforms to the specification
and validates the app.json file. It creates a compressed file called <app_name>.aci
where app name is taken from app.json. The ouput is created in the same directory
where the app files are located.

Instructions for installing Cisco ACI app packager requirements
---------------------------------------------------------------

1. Download the app packager archive (cisco_aci_app_packager.tar.gz)
2. Execute: pip install /path/to/cisco_aci_app_packager.tar.gz
3. Uncompress the cisco_aci_app_packager.tar.gz file. It will create a directory
   named cisco_aci_app_packager/
4. The packager is located at cisco_aci_app_packager/packager/aci_app_packager.py

Execution
---------
Package app along with signature and provide two command line arguments
1. absolute path to directory where app files are located
2. absolute path of file with private key

Example:
If /home/sunverma/my_app directory contains all the app files
and /home/sunverma/private_key.pem contains the private key

Packaging my_app with signature
$ python aci_app_packager.py -f /home/sunverma/my_app -p /home/sunverma/private_key.pem

Packaging my_app without signature
$ python aci_app_packager.py -f /home/sunverma/my_app

This script uses the "aci_app_validator.py" for package and file validation,
hence aci_app_validator.py should be located in the same directory where
pakaging script is running. 

Contact: Sunil Verma (sunverma), Aravind Ganesan (aravgane)
Copyright (c) 2016 Cisco Systems Inc. All rights reserved.
