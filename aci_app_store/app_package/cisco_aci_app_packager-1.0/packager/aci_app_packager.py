"""
Copyright (c) 2016 Cisco Systems Inc. All rights reserved.
Cisco ACI app packager script

This script will validate if the directory structure conforms to the specification 
and validates the app.json file. It creates a compressed file called <app_name>.aci
where app name is taken from app.json. The ouput is created in the same directory 
where the app files are located.

Execution
---------
Package app along with signature and provide two command line arguments
1. absolute path to directory where app files are located
2. absolute path of file with private key

Example:
If /home/sunverma/my_app directory contains all the app files
and /home/sunverma/private_key.pem contains the private key

Goto to script directory
$ cd /cisco/aci_app_venv

Packaging my_app with signature
$ /cisco/aci_app_venv/bin/python aci_app_packager.py -f /home/sunverma/my_app -p /home/sunverma/private_key.pem

Packaging my_app without signature
$ /cisco/aci_app_venv/bin/python aci_app_packager.py -f /home/sunverma/my_app

This script uses the "aci_app_validator.py" for package and file validation, 
hence aci_app_validator.py should be located in the same directory where 
pakaging script is running. File named cisco_license.txt should also be 
located in the same directory as the packager.

Contact: Sunil Verma (sunverma), Aravind Ganesan (aravgane)
Copyright (c) 2016 Cisco Systems Inc. All rights reserved.
"""

import os
import argparse
import shutil
import json
import tarfile
import zipfile
import hashlib
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA
import sys
from distutils.dir_util import copy_tree
import logging
import commands
import aci_app_validator

def print_and_log(msg):
    print str(msg)
    logger.info(str(msg))

def print_and_log_error(msg):
    print str(msg)
    logger.error(str(msg))

class Packager(object):
    def __init__(self):
        self.err_msg = ''
        self.err_code = 255
        self.outputDir = ''
        self.scriptDir = ''
        self.tmpfileLoc = ''
        self.tmpAppDir = ''
        self.inputAppDir = ''
        self.appFileName = ''
        self.appDirName = ''
        self.signedAppFile = ''

    #Calculate hash,signature
    def calculateSignature(self):
        logger.info('Calulating hash of app folder')
        h = hashlib.sha256()
        hash_value=self.hash_dir(self.tmpAppDir)
        logger.info('Successfully calculated hash, value is: %s' %(hash_value))
        fd = open(self.privateKeyPath, 'r')
        key_data = fd.read()
        fd.close()
        try:
            key = RSA.importKey(key_data)
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            print_and_log_error('Error: Failed to import private key')
            os.chdir(orig_wk_dir)
            return 1
        try:
            signature = key.sign(hash_value, '')
            os.chdir(self.inputAppDir)
            sigFile = self.appDirName + '.dev.signature'
            logger.info('Creating signature file {0} inside package'.format(sigFile))
            if os.path.exists(self.tmpfileLoc) == False:
                logger.info('Creating directory {0}'.format(self.tmpfileLoc))
                os.mkdir(self.tmpfileLoc,0o755)
            os.chmod(self.tmpfileLoc, 0o755)
            os.chdir(self.tmpfileLoc)
            with open(sigFile, "w+") as fh:
                fh.write(str(signature[0]))
                fh.close()
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            print_and_log_error('Error: Signature generation failed')
            os.chdir(orig_wk_dir)
            return 1
        logger.info('Successfully generated signature %s' %(str(signature[0])))
        return 0

    #Calculate hash value and return value to calculateSignature
    def hash_dir(self,directory):
        hashes = []
        for path, dirs, files in os.walk(directory):
            for file in sorted(files):
                con=os.path.join(path, file)
                sha = hashlib.sha1()
                with open(con, 'rb') as f:
                    while True:
                        block = f.read(2**10)
                        if not block: break
                        sha.update(block)
                    sh1=sha.hexdigest()
                hashes.append(sh1)
            for dir in sorted(dirs):
                hashes.append(self.hash_dir(os.path.join(path, dir)))
            break
        return str(hash(''.join(hashes)))

    def copying_Directories(self,fromDir,toDir,directory):
        fromDirectory = fromDir + '/' + directory
        toDirectory = toDir + '/' + directory
        copy_tree(fromDirectory, toDirectory)

    # Copying app files and folder to temporary folder for compressing
    def copy_function(self):
        try:
            os.chdir(self.inputAppDir)
            if not os.path.exists(self.tmpfileLoc):
                logger.info('Creating directory {0}'.format(self.tmpfileLoc))
                os.mkdir(self.tmpfileLoc,0o755)
            os.chmod(self.tmpfileLoc, 0o755)
            if not os.path.exists(self.tmpAppDir):
                logger.info('Creating directory {0}'.format(self.tmpAppDir))
                os.mkdir(self.tmpAppDir,0o755)
            os.chmod(self.tmpAppDir, 0o755)
            from shutil import copyfile
            srcFile=self.inputAppDir + '/' + 'app.json'
            dstFile=self.tmpAppDir + '/' + 'app.json'
            copyfile(srcFile, dstFile)
            self.copying_Directories(self.inputAppDir,self.tmpAppDir,"Media")
            self.copying_Directories(self.inputAppDir,self.tmpAppDir,"UIAssets")
            self.copying_Directories(self.inputAppDir,self.tmpAppDir,"Legal")
            if os.path.exists('Service'):
                self.copying_Directories(self.inputAppDir,self.tmpAppDir,"Service")
                self.copying_Directories(self.inputAppDir,self.tmpAppDir,"Image")
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            print_and_log_error('Error: Failed to import private key')
            os.chdir(orig_wk_dir)
            return 1
        return 0

    # Compress the app folder contents into <appname>.aci file
    def make_aci(self):
        try:
            os.chdir(self.tmpfileLoc)
            cmd = 'zip -r {0} *'.format(self.signedAppFile)
            rc = commands.getstatusoutput(cmd)
            if rc[0]:
                raise Exception()
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            print_and_log_error('Error: Failed to compress and create app')
            os.chdir(orig_wk_dir)
            return 1
        '''
        MBFACTOR = float(1<<20)
        size_App=os.path.getsize(self.tmpfileLoc + '/' + self.appDirName)/MBFACTOR
        g = float("{0:.2f}".format(size_App))
        if(size_App>1000):
            print ("Size of app :"+app_name+" should be less than 1000 MB,current file size is : "+str(g)+" MB")
            logger.error('Size of <app.aci>  should be less than 1000 MB')
            return 1
        '''
        return 0

    def main(self, input_app_dir, private_key_path, validate_only=False):
        self.outputDir = outputDir
        self.scriptDir = scriptDir
        self.inputAppDir = input_app_dir
        self.privateKeyPath = private_key_path

        if self.inputAppDir is None or os.path.isdir(self.inputAppDir)==False:
            print_and_log_error('Invalid path to app directory: {0}'.format(self.inputAppDir))
            return 1

        if self.privateKeyPath is not None and os.path.isfile(self.privateKeyPath)==False:
            print_and_log_error('Invalid path to private key file: {0}'.format(self.privateKeyPath))
            return 1

        logger.info('Running Packager Utility')
        logger.info('Input path to app directory: %s' %(self.inputAppDir))
        logger.info('Input path to private key: %s' %(self.privateKeyPath))

        if self.inputAppDir[-1] == '/':
            self.inputAppDir = self.inputAppDir[:-1]
        os.chdir(self.inputAppDir)
        try:
            data = json.load(open('app.json', 'r'))
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            print_and_log_error('{0}/app.json is not valid JSON format - unable to load file'.format(self.inputAppDir))
            os.chdir(orig_wk_dir)
            sys.exit(1)
        try:
            appid=data['appid']
            name=data['name']
            vendor=data['vendor']
            vendordomain=data['vendordomain']
            version=data['version']
            apicversion=data['apicversion']
            author=data['author']
            shortdescr=data['shortdescr']
            iconfile=data['iconfile']
            category=data['category']
            permissions=data['permissions']
            permissionslevel=data['permissionslevel']
        except Exception as e:
            if len(str(e)):
                print_and_log_error('{0}/app.json has invalid metadata - {1} is missing'.format(self.inputAppDir, e))
            else:
                print_and_log_error('{0}/app.json has invalid metadata'.format(self.inputAppDir))
            os.chdir(orig_wk_dir)
            sys.exit(1)

        # Check if app.ver exists, if yes update the version in app.jon before packaging
        try:
            if os.path.isfile('app.ver'):
                file = open('app.ver', 'r')
                new_version = file.read()
                new_version = new_version.strip()
                data['version'] = new_version
                logger.info('Found app.ver, updating version in app.json to {0}'.format(new_version))
            # Update app.json
            with open('app.json', 'w') as outfile:
                json.dump(data, outfile, indent=4, sort_keys=True, separators=(',', ':'))
        except Exception as e:
            if len(str(e)):
                print_and_log_error('Error updating version in app.json from app.ver - {0}'.format(e))
            else:
                print_and_log_error('Error updating version in app.json from app.ver')
            os.chdir(orig_wk_dir)
            sys.exit(1)

        self.appDirName=data['vendordomain']+"_"+data['appid']
        self.appFileName=data['vendordomain']+"-"+data['appid']+"-"+data['version']+".aci"
        self.tmpfileLoc = self.inputAppDir + '/' + self.appFileName
        self.tmpAppDir = self.inputAppDir + '/' + self.appFileName + '/' + self.appDirName
        self.signedAppFile = self.outputDir + '/' + self.appFileName
        if os.path.exists(self.tmpfileLoc) == True:
            shutil.rmtree(self.tmpfileLoc)

        # Invoking Validator class from validationsvc.py
        validator=aci_app_validator.Validator()
        appState=validator.get_State(self.inputAppDir)
        logger.info('App state is: {0}'.format(appState))

        # Validating directory structure
        rc, msg = validator.checkMandatoryFiles(self.inputAppDir,"packager",appState,scriptDir=self.scriptDir)
        if rc != 0:
            print_and_log_error('Validation of mandatory files and directories failed')
            return rc
        print_and_log("Validation of mandatory files and directories successful")

        # Get app meta data
        rc, msg = validator.getAppMetaData(self.inputAppDir,"packager",appState)
        if rc != 0:
            print_and_log_error('Retrieving app meta data failed')
            return rc
        print_and_log('Retrieving app meta data successful')

        # Validate app meta data
        rc, msg = validator.validateAppMetaData("packager",appState)
        if rc != 0:
            print_and_log_error('Validation of app meta data failed')
            return rc
        print_and_log('Validation of app meta data successful')

        if validate_only:
            print_and_log('App successfully validated - {0}'.format(self.inputAppDir))
            return 'OK'

        # Copy app files and package the same
        logger.info('Copying app folders into the package')
        rc = self.copy_function()
        if rc != 0:
            print_and_log_error('Copying app files and folders failed')
            return rc
        logger.info('Successfully copied folders into the package')

        # Calculate signature
        logger.info('Checking if private key exists in the specified path')
        if self.privateKeyPath is not None:
            logger.info('Private key file present in specified directory')
            if self.calculateSignature() != 0:
                return 1

        # Compress app files and folders into .aci file
        logger.info('Compressing the package into .aci file')
        rc = self.make_aci()
        if rc != 0:
            print_and_log_error('Compressing of app files and folders failed')
            return rc
        logger.info('Compressing of app files and folders successful')

        # Cleaning up temporary files and directories
        if os.path.exists(self.tmpfileLoc) == True:
            logger.info('Cleaning up temp directory {0}'.format(self.tmpfileLoc))
            shutil.rmtree(self.tmpfileLoc)

        print_and_log('App successfully packaged - {0}'.format(self.signedAppFile))
        return 0

if __name__ == '__main__':
    # Parse command line arguments
    from argparse import RawTextHelpFormatter
    parser = argparse.ArgumentParser(description='Utility to package ACI app files\n\nThis script will validate if the directory structure conforms to the specification\nand validates the app.json file. It creates a compressed file called <app_name>.aci\nwhere app name is taken from app.json. The ouput is created in the same directory\nwhere the app files are located.\n\nExample:\nIf /home/sunverma/my_app directory contains all the app files\nand /home/sunverma/private_key.pem contains the private key\n\nGoto to script directory\n$ cd /cisco/aci_app_venv\n\nPackaging my_app with signature\n$ /cisco/aci_app_venv/bin/python aci_app_packager.py -f /home/sunverma/my_app -p /home/sunverma/private_key.pem\n\nPackaging my_app without signature\n$ /cisco/aci_app_venv/bin/python aci_app_packager.py -f /home/sunverma/my_app', formatter_class=RawTextHelpFormatter)
    parser.add_argument('-f', dest='file_path', help='Full path to ACI app directory')
    parser.add_argument('-p', dest='private_key_path', help='Full path to developer\'s private key')
    parser.add_argument("--logfile", type=str, default='./aci_app_packager.log', help="Full path to log file")
    parser.add_argument("--validate", dest='validate_only', help='Only validates the application without packaging it.', action='store_true')
    args = parser.parse_args()

    # Setup logging
    fStr='%(asctime)s %(levelname)5s %(name)s(%(lineno)s) %(message)s'
    logging.basicConfig(filename=args.logfile, format=fStr, level=logging.DEBUG)
    logger = logging.getLogger('packager')

    scriptDir=os.path.dirname(os.path.abspath(__file__))
    outputDir=os.path.abspath(os.path.join(args.file_path, os.pardir))
    logging.debug('args: {0}'.format(args))
    logging.debug('scriptDir: {0}'.format(scriptDir))
    logger.debug('outputDir: {0}'.format(outputDir))

    orig_wk_dir = os.getcwd()
    packager = Packager()
    rc = packager.main(args.file_path,args.private_key_path, args.validate_only)
    os.chdir(orig_wk_dir)
    if rc != 0:
        print_and_log_error('Error: Failed to package app - {0}'.format(args.file_path))
        sys.exit(rc)
