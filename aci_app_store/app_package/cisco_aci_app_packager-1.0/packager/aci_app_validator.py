"""
Copyright (c) 2016 Cisco Systems Inc. All rights reserved.
Cisco ACI app validation script

This script runs a flask server which validates an aci app. The HTTP request
for app signin should include following parameters in the query string:

. filename - full path and filename of the app to be signed
. outputDir - full path of the output directory where signed app will be kept
. sourceDir - full path of the source directory where app to be signed is kept
. publicKeyPath - full path to public key file

Example:
http://localhost:8080/cisco_sign?filename=Cisco-VisuDash-2.2-0.69a.aci&sourceDir=%2Ftmp%2Fappstore_utils&outputDir=%2Ftmp%2Foutputdir
http://localhost:8080/cisco_sign?filename=Cisco-VisuDash-2.2-0.69a.aci&sourceDir=%2Ftmp%2Fappstore_utils&outputDir=%2Ftmp%2Foutputdir&publicKeyPath=%2Fhome%2Fmagento%2FsourceDir%2Fpublic.pem

Image validation process:

1. Extract imge under a directory in outputDir
2. Validate app.json entries
3. Validate app directory structure and contents

How to run the server:
$ bash start_server.sh <IP> <PORT>

IP and PORT are optional.
Default values are:
IP: 0.0.0.0
PORT: 8080

For UNIT TEST, provide use following query:
$ curl http://localhost:8080/validate?UT=True

Create a json file titled app.json in the home directory and populate the
required values. This code assumes the json file that is input is part of
a stateless app. To validate a json file part of stateful app (without
/service directory), you need to assign the global variable unitTestAppState
to "stateful"

Contact: Sunil Verma (sunverma), Aravind Ganesan (aravgane)
Copyright (c) 2016 Cisco Systems Inc. All rights reserved.
"""

#########################################################################
### This file should not have any print statement for callType 'apic' ###
#########################################################################

import os
import logging
import time
import tempfile
import glob
import math
import uuid
import json
import tarfile
import zipfile
import hashlib
import commands
from Crypto.PublicKey import RSA
# import validators
# import magic

# Setup the logger
logger = logging.getLogger('validator')

# For unit test purpose only:
unitTestAppState="stateless"
contactFieldPresent=False
apiFieldPresent=False

# Class to extract the given file into the outputDir directory
class CreateExtractDir(object):
    def __init__(self, outputDir=None, isDir=False, size_in_gb=3):
        dirname = None
        try:
            if 0 != os.system('mkdir -p %s > /dev/null 2>&1' % outputDir):
                logger.info('Error occurred ' )
            s = os.statvfs(outputDir)
            fs = s.f_bsize * s.f_bavail
            if fs < size_in_gb * math.pow(10,9):
                logger.warn('Not enough space on %c (avail=%d)' % (outputDir, fs))
                err_code = 200
                err_msg = 'Not enough space on device'
            test_file = '%s/appstore-test-%d' % (outputDir, time.time())
            open(test_file, 'a').close()
            os.remove(test_file)
            dirname = outputDir
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            pass
        if dirname == None:
            dirname = outputDir
        if outputDir:
            lprefix = 'appstore-' + os.path.basename(outputDir) + '-'
        else:
            lprefix = 'appstore-'
        if not isDir:
            if not lprefix:
                lprefix = 'noprefix'
            self.name = os.path.join(dirname, '%s-%s' % (lprefix, uuid.uuid4()))
        else:
            self.name = tempfile.mkdtemp(prefix = lprefix, dir = dirname)
        logger.info('Created: ' + self.name)

    def release(self):
        try:
            logger.info('Releasing: ' + self.name)
            if self.name:
                rc = os.system('rm -rf %s' % self.name)
            if rc != 0:
                logger.error('Failed to remove %s' % self.name)
            self.name = None
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            logger.error('Failed to release: %s' % self.name)

    def __str__ (self):
        return self.name

class Validator(object):
    def __init__(self):
        self.appDir = ''
        self.appExtractLoc = ''
        self.appFilename = ''
        self.appMeta = ''
        self.err_code = 255
        self.err_msg = ''
        self.outputDir = ''
        self.sourceDir = ''
        self.appId = ''
        self.version = ''
        self.iconFile = ''
        self.author = ''
        self.signature = ''
        self.UT = False

    def fileExist(self, filename):
        if not os.path.isfile(filename):
            self.err_code = 201
            self.err_msg = 'File {0} does not exists'.format(filename)
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            raise Exception()

    def setLogger(self, logDir, callType=None):
        global logger

        # Logger setting when this file is called from fwhdr.py
        if callType != 'apic':
            return

        hdlr = logging.FileHandler(logDir)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        hdlr.setFormatter(formatter)
        logger.addHandler(hdlr) 
        logger.setLevel(logging.DEBUG)
        logger.info('Validator log directory: {0}'.format(logDir))

    #Extracting the tar file into the output directory,setting permission
    def extractFiles(self, filename, extractLoc):
        try:
            if os.path.isdir(extractLoc)==False:
                os.mkdir(extractLoc,0o777)
            self.appExtractLoc = CreateExtractDir(extractLoc, True)
            logger.info('App extract dir is {0}'.format(self.appExtractLoc))
            os.chdir(str(self.appExtractLoc))
            if tarfile.is_tarfile(filename):
                cmd = 'tar xvfz {0}'.format(filename)
                os.system(cmd)
            elif zipfile.is_zipfile(filename):
                cmd = 'unzip {0}'.format(filename)
                os.system(cmd)
            else:
                self.err_code = 202
                self.err_msg = '{0} has invalid compression, expecting zip file'.format(filename)
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                raise Exception()
                return self.err_code

            string_appDir=str(self.appExtractLoc)
            for dirpath, dirnames, filenames in os.walk(string_appDir):
                for dirname in dirpath:
                    path = os.path.join(dirpath, dirname)
                    os.chmod(dirpath, 0o777)
                for filename in filenames:
                    path = os.path.join(dirpath, filename)
                    os.chmod(path, 0o777)
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            self.err_code = 203
            self.err_msg = 'Failed to extract file ' + filename
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            raise Exception()
            return self.err_code
        return 0

    def getResult(self):
        if (self.err_code != 0):
            result = [{ 'status' : 'failed'}, {'errCode' : self.err_code, 'errMsg' : self.err_msg}]
        else:
            result = [{ 'status' : 'ok'}, { 'appMeta': self.appMeta}]
        return result

    # Raise exceptions when validator is executed, it throws exception in JSON format to the browser
    # When validator is called from packager, it prints the exception message to the console
    # When validator is called from apic, it does not print anythin
    def exception_type(self,callType,err_code,err_msg):
        if callType == 'packager':
            print 'Error: {0}'.format(err_msg)
        elif callType == 'apic':
            pass
        else:
            raise Exception()

    # This method checks if the mandatory fields are present in the app.json
    def validateMandatoryFields(self,filename,callType,appState):
        with open(filename) as data_file:
            data = json.load(data_file)
        if 'appid' not in data:
            self.err_code = 10
            self.err_msg = 'Appid field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'version' not in data:
            self.err_code = 11
            self.err_msg = 'Version field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'iconfile' not in data:
            self.err_code = 12
            self.err_msg = 'Iconfile field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'name' not in data:
            self.err_code = 13
            self.err_msg = 'Name field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'shortdescr' not in data:
            self.err_code = 14
            self.err_msg = 'Shortdescr field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'vendor' not in data:
            self.err_code = 15
            self.err_msg = 'Vendor field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'apicversion' not in data:
            self.err_code = 16
            self.err_msg = 'Apicversion field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'author' not in data:
            self.err_code = 17
            self.err_msg = 'Author field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'category' not in data:
            self.err_code = 18
            self.err_msg = 'Category field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'vendordomain' not in data:
            self.err_code = 19
            self.err_msg = 'Vendordomain field missing in JSON file'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'permissions' not in data:
            self.err_code = 20
            self.err_msg = "Permissions field missing in JSON file"
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'permissionslevel' not in data:
            self.err_code = 21
            self.err_msg = "Permissions level field missing in JSON file"
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if 'contact' in data:
            contactFieldPresent=True
        if appState == "stateful":
            if 'api' not in data:
                self.err_code = 22
                self.err_msg = "Api field missing in JSON file for stateful app"
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
            '''
            if 'getStats' not in data['api']:
                self.err_code = 22
                self.err_msg = 'api getStats is required for an app with /service directory.'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
            if 'setQos' not in data['api']:
                self.err_code = 22
                self.err_msg = 'api setQos is required for an app with /service directory.'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
            '''
        if appState == "stateless":
            if 'api' in data:
                self.err_code = 22
                self.err_msg = "Api field in JSON file should only be specified for stateful app"
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
        return 0

    #Get hash of the directory
    def hash_dir(self,dir_path):
        hashes = []
        for path, dirs, files in os.walk(dir_path):
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

    # Verify the signature
    def validateSignature(self,extracted_directory_location):
        subdir=str(next(os.walk(extracted_directory_location))[1])
        size=len(subdir)-2
        subdir1=subdir[2:size]
        appFolder=extracted_directory_location+"/"+subdir1+"/"
        logger.info('Calculating hash for directory {0}'.format(appFolder))
        h1=self.hash_dir(appFolder)
        logger.info('Hash: {0}'.format(h1))
        signature_filename=extracted_directory_location+"/"+subdir1+".dev.signature"
        logger.info('Signature file is {0}'.format(signature_filename))
        if(os.path.exists(signature_filename)==False):
            self.err_code = 51
            self.err_msg = "Signature file {0} does not exist".format(signature_filename)
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        try:
            signature = open(signature_filename, "r").read()
            signature2=(int(signature))
            signature_tuple=(signature2,)
            pub_key = open(self.publicKeyPath, "r").read()
            rsakey = RSA.importKey(pub_key)
            rsakey=rsakey.publickey()
            if rsakey.verify(h1,signature_tuple):
                logger.info('Signature Verified, proceeding to validate contents')
                return 0
            else:
                self.err_code = 52
                self.err_msg = 'Signature verification failed'
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                return self.err_code
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            self.err_code = 53
            self.err_msg = 'Error during signature verification'
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            return self.err_code
        return 0

    #Classify the app as stateful ( with /Service directory ) or stateless (without /Service directory)
    #Checking if mandatory files/directories are present
    def mandatoryFileCheck(self,filename,extractLoc):
        logger.info('Validating app directory and file structure')
        subdir=str(next(os.walk(str(self.appExtractLoc)))[1])
        size=len(subdir)-2
        subdir1=subdir[2:size]
        appFolder=str(self.appExtractLoc)+"/"+subdir1+"/"
        os.chdir(appFolder)
        appState=self.get_State(appFolder)
        rc, msg = self.checkMandatoryFiles(appFolder,"website",appState)
        if rc != 0:
            raise Exception()
            return rc
        logger.info('Validation of directory and file structure successful')
        return 0

    #Check if /Service directory exists
    def get_State(self,appFolder):
        os.chdir(appFolder)
        if os.path.exists('Service') == True:
            return "stateful"
        else:
            return "stateless"

    #Checking if mandatory files/directories exist
    def checkMandatoryFiles(self, extractLoc, callType, appState, scriptDir=''):
        os.chdir(extractLoc)
        permittedFileAndDir=["UIAssets","Service","Media","Image","Legal","app.json","app.ver"]
        retrievedFiles=glob.glob('*')
        if not set(retrievedFiles).issubset(set(permittedFileAndDir)):
            diff = set(retrievedFiles).difference(set(permittedFileAndDir))
            self.err_code = 101
            self.err_msg = 'Following files and directories are not allowed in the app - {0}'.format(', '.join(diff))
            logger.error('Error occurred: %d %s'%(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code, self.err_msg
        if os.path.isfile('app.json') == True:
            json_filename=extractLoc+"app.json/"
        else:
            self.err_code = 102
            self.err_msg ="App meta file app.json does not exist"
            logger.error('Error occurred: %d %s'%(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code, self.err_msg
        if os.path.exists('UIAssets') == True:
            os.chdir('./UIAssets')
            if os.path.isfile('app.html') == False:
                self.err_code = 103
                self.err_msg ="Required file app.html does not exist inside UIAssets directory"
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
            if os.stat('app.html').st_size == 0:
                self.err_code = 103
                self.err_msg ="Required file app.html inside UIAssets directory cannot be empty"
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
        else:
            self.err_code = 104
            self.err_msg ="Required directory UIAssets does not exist"
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code, self.err_msg
        os.chdir(extractLoc)
        if callType == "packager" and os.path.exists('Legal') == True:
            try:
                os.chdir('./Legal')
                ciscoEula = scriptDir + '/Cisco_App_Center_Customer_Agreement.docx'
                if not os.path.isfile('Cisco_App_Center_Customer_Agreement.docx'):
                    if os.path.isfile(ciscoEula) == False:
                        self.err_code = 105
                        self.err_msg ="File Cisco_App_Center_Customer_Agreement.docx not present in same directory as packager"
                        logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                        self.exception_type(callType,self.err_code,self.err_msg)
                        return self.err_code, self.err_msg
                    cmd="cp -f {0} .".format(ciscoEula)
                    logger.info("Adding file to Legal directory - {0}".format('Cisco_App_Center_Customer_Agreement.docx'))
                    os.system(cmd)
                ciscoExportQ = scriptDir + '/Cisco_App_Center_Export_Compliance_Questionnaire.docx'
                if not os.path.isfile('Cisco_App_Center_Export_Compliance_Questionnaire.docx'):
                    if os.path.isfile(ciscoExportQ) == False:
                        self.err_code = 105
                        self.err_msg ="File Cisco_App_Center_Export_Compliance_Questionnaire.docx not present in same directory as packager"
                        logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                        self.exception_type(callType,self.err_code,self.err_msg)
                        return self.err_code, self.err_msg
                    cmd="cp -f {0} .".format(ciscoExportQ)
                    logger.info("Adding file to Legal directory - {0}".format('Cisco_App_Center_Export_Compliance_Questionnaire.docx'))
                    os.system(cmd)
            except Exception as e:
                self.err_code = 105
                self.err_msg ="Error while Legal directory content creation - {0}".format(str(e))
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
        # Legal directory is stripped from cisco signed image
        # it should not be verified on apic
        os.chdir(extractLoc)
        if callType != 'apic':
            if os.path.exists('Legal') == True:
                # Check for contents of legal directory
                os.chdir('./Legal')
                files=glob.glob("*")
                if not len(files):
                    self.err_code = 105
                    self.err_msg ="Legal directory cannot be empty"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if os.path.isfile('Cisco_App_Center_Customer_Agreement.docx') == False:
                    self.err_code = 105
                    self.err_msg ="Required file Cisco_App_Center_Customer_Agreement.docx does not exist inside Legal directory"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if os.stat('Cisco_App_Center_Customer_Agreement.docx').st_size == 0:
                    self.err_code = 105
                    self.err_msg ="Required file Cisco_App_Center_Customer_Agreement.docx inside Legal directory cannot be empty"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if os.path.isfile('Cisco_App_Center_Export_Compliance_Questionnaire.docx') == False:
                    self.err_code = 105
                    self.err_msg ="Required file Cisco_App_Center_Export_Compliance_Questionnaire.docx does not exist inside Legal directory"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if os.stat('Cisco_App_Center_Export_Compliance_Questionnaire.docx').st_size == 0:
                    self.err_code = 105
                    self.err_msg ="Required file Cisco_App_Center_Export_Compliance_Questionnaire.docx inside Legal directory cannot be empty"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
            else:
                self.err_code = 106
                self.err_msg ="Required directory Legal does not exist"
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
        if appState == "stateful":
            os.chdir(extractLoc)
            if os.path.exists('Service') == True:
                os.chdir('./Service')
                if os.path.isfile('start.sh') == False:
                    self.err_code = 107
                    self.err_msg ="Required file start.sh does not exist inside Service directory"
                    logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if os.stat('start.sh').st_size == 0:
                    self.err_code = 107
                    self.err_msg ="Required file start.sh inside Service directory cannot be empty"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
            else:
                self.err_code = 108
                self.err_msg ="Required directory Service does not exist"
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
            os.chdir(extractLoc)
            if os.path.exists('Image') == True:
                # Check for contents of image directory
                os.chdir('./Image')
                files=glob.glob("*")
                if not len(files):
                    self.err_code = 109
                    self.err_msg ="Image directory cannot be empty"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if callType != 'apic' and len(files) > 1:
                    self.err_code = 109
                    self.err_msg ="Only one docker image file is permitted inside Image "
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                pass
            else:
                self.err_code = 110
                self.err_msg ="Required directory Image does not exist"
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
        os.chdir(extractLoc)
        if os.path.exists('Media') == True:
            os.chdir('./Media')
            permittedDir=["Snapshots","ReleaseNotes","Readme","License","IntroVideo"]
            retrievedFiles=glob.glob('*')
            if not set(retrievedFiles).issubset(set(permittedDir)):
                diff = set(retrievedFiles).difference(set(permittedDir))
                self.err_code = 111
                self.err_msg = 'Following files and directories are not allowed under Media - {0}'.format(', '.join(diff))
                logger.error('Error occurred: %d %s'%(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
            if os.path.exists('./Readme') == True:
                os.chdir('./Readme')
                readme= glob.glob("*")
                if os.path.isfile('readme.txt') == False:
                    self.err_code = 112
                    self.err_msg ="Required file readme.txt does not exist inside Readme directory"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if os.stat('readme.txt').st_size == 0:
                    self.err_code = 112
                    self.err_msg ="Required file readme.txt inside Readme directory cannot be empty"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if(len(readme)>1):
                    self.err_code = 113
                    self.err_msg ="Only one file of type .txt is permitted inside Readme directory"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                '''
                if(len(readme)>0):
                    fileType=magic.from_file(readme[0])
                    fileType=fileType[0:5]
                    if(fileType!="ASCII"):
                        self.err_code = 114
                        self.err_msg =readme[0]+" is not valid .txt file, the file needs to have some ASCII content"
                        logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                        self.exception_type(callType,self.err_code,self.err_msg)
                        return self.err_code, self.err_msg
                '''
            else:
                self.err_code = 115
                self.err_msg ="Required directory Readme does not exist inside Media directory"
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
            os.chdir(extractLoc)
            os.chdir('./Media')
            if os.path.exists('./ReleaseNotes') == True:
                os.chdir('./ReleaseNotes')
                releasenotes= glob.glob("*")
                '''
                if(len(releasenotes)>0):
                    fileType=magic.from_file(releasenotes[0])
                    fileType=fileType[0:5]
                    if(fileType!="ASCII"):
                        self.err_code = 116
                        self.err_msg =releasenotes[0]+" is not valid .txt file, the file needs to have some ASCII content"
                        logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                        self.exception_type(callType,self.err_code,self.err_msg)
                        return self.err_code, self.err_msg
                '''
                if(len(releasenotes)>1):
                    self.err_code = 117
                    self.err_msg ="Only one file of type .txt is permitted inside ReleaseNotes directory"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
            os.chdir(extractLoc)
            os.chdir('./Media')
            if callType=="packager" and not os.path.exists('./License'):
                try:
                    msg="License directory not found, adding License directory"
                    logger.info(msg)
                    os.mkdir('License')
                except Exception as e:
                    self.err_code = 119
                    self.err_msg ="Error while creating License directory - {0}".format(str(e))
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
            if os.path.exists('./License') == True:
                os.chdir('./License')
                license= glob.glob("*")
                if callType=="packager":
                    try:
                        ciscoLicenseFile = scriptDir + '/Cisco_App_Center_License.txt'
                        if not os.path.isfile('Cisco_App_Center_License.txt'):
                            if os.path.isfile(ciscoLicenseFile) == False:
                                self.err_code = 119
                                self.err_msg ="File Cisco_App_Center_License.txt not present in same directory as packager"
                                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                                self.exception_type(callType,self.err_code,self.err_msg)
                                return self.err_code, self.err_msg
                            cmd="cp -f {0} Cisco_App_Center_License.txt".format(ciscoLicenseFile)
                            logger.info("Adding Cisco license file - {0}".format('Cisco_App_Center_License.txt'))
                            os.system(cmd)
                    except Exception as e:
                        self.err_code = 119
                        self.err_msg ="Error while adding Cisco license - {0}".format(str(e))
                        logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                        self.exception_type(callType,self.err_code,self.err_msg)
                        return self.err_code, self.err_msg
                license= glob.glob("*")
                if(len(license)>2):
                    self.err_code = 119
                    self.err_msg ="Only two files Developer License and Cisco_App_Center_License.txt are permitted inside License directory"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if os.path.isfile('Cisco_App_Center_License.txt') == False:
                    self.err_code = 119
                    self.err_msg ="Mandatory file Cisco_App_Center_License.txt does not exist inside License directory"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if os.stat('Cisco_App_Center_License.txt').st_size == 0:
                    self.err_code = 119
                    self.err_msg ="Mandatory file Cisco_App_Center_License.txt inside License directory cannot be empty"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
            else:
                self.err_code = 119
                self.err_msg ="Required directory License does not exist"
                logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
            os.chdir(extractLoc)
            os.chdir('./Media')
            MBFACTOR = float(1<<20)
            if os.path.exists('./IntroVideo') == True:
                os.chdir('./IntroVideo')
                videoFile= glob.glob("*")
                if(len(videoFile)>1):
                    self.err_code = 120
                    self.err_msg ="Only one file of type .mp4 is permitted inside IntroVideo directory"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                '''
                if(len(videoFile)>0):
                    fileType=magic.from_file(videoFile[0])
                    fileType=fileType[0:13]
                    if(fileType=="ISO Media, MP"):
                        size_VideoFile=os.path.getsize(videoFile[0])/MBFACTOR
                        g = float("{0:.2f}".format(size_VideoFile))
                        if(size_VideoFile>100):
                            self.err_code = 121
                            self.err_msg ="Size of video file should be less than 10MB,current file size is : "+str(g)+" MB"
                            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                            self.exception_type(callType,self.err_code,self.err_msg)
                            return self.err_code, self.err_msg
                    else:
                        self.err_code = 122
                        self.err_msg =videoFile[0]+" is not valid mp4 file, the file needs to have some video content"
                        logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                        self.exception_type(callType,self.err_code,self.err_msg)
                        return self.err_code, self.err_msg
                '''
            os.chdir(extractLoc)
            os.chdir('./Media')
            if os.path.exists('./Snapshots') == True:
                flag=0
                os.chdir('./Snapshots')
                allFiles= glob.glob("*")
                types = ('*.png', '*.gif','*.jpg') # the tuple of file types
                imageFiles= []
                for files in types:
                    imageFiles.extend(glob.glob(files))
                if(len(allFiles) != len(imageFiles)):
                    self.err_code = 123
                    self.err_msg ="Snapshots should only contain files of type .jpg or .gif or .png"
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                '''
                else:
                    for i in imageFiles:
                        fileType=magic.from_file(i)
                        fileType=fileType.split(",")[0]
                        fileType=fileType[0:9]
                        if((fileType!="PNG image") and (fileType!="JPEG image") and (fileType!="GIF image")):
                            self.err_code = 124
                            self.err_msg =i+" is not a valid image file, it needs to have proper image"
                            logger.error('Error occurred: %d %s'%(self.err_code, self.err_msg))
                            self.exception_type(callType,self.err_code,self.err_msg)
                            return self.err_code, self.err_msg
                        else:
                            flag=1
                '''
        else:
            self.err_code = 125
            self.err_msg ="Required directory Media does not exist"
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code, self.err_msg
        return 0, ''

    # Method to retreive the values from app.json file
    def getAppMetaData(self, extractLoc, callType, appState, isUnitTest=False):
        logger.info('Retrieving app meta data')
        if callType=="packager" or callType=="apic":
            os.chdir(extractLoc)
            json_file=extractLoc+'/app.json'
            try:
                self.appMeta = json.load(open(('app.json'), 'r'))
            except Exception as e:
                if len(str(e)):
                    logger.error(str(e))
                self.err_code = 150
                self.err_msg = 'Invalid app meta data, meta data is not in valid JSON file'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
            if self.validateMandatoryFields(json_file,callType,appState) != 0:
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code, self.err_msg
            media_path=extractLoc+"/Media"
            self.appMeta["iconfile"] = extractLoc+"/UIAssets/" + self.appMeta["iconfile"]
            self.appMeta["media"] = {}
            self.appMeta["media"]["readme"] = glob.glob(media_path+"/Readme/*")
            self.appMeta["media"]["license"] = glob.glob(media_path+"/License/*")
            self.appMeta["media"]["introvideo"] = glob.glob(media_path+"/IntroVideo/*")
            self.appMeta["media"]["snapshots"] = glob.glob(media_path+"/Snapshots/*")
            self.appMeta["media"]["release-notes"] = glob.glob(media_path+"/ReleaseNotes/*")
        else:
            if isUnitTest:
                try:
                    self.appMeta = json.load(open(('app.json'), 'r'))
                except Exception as e:
                    if len(str(e)):
                        logger.error(str(e))
                    self.err_code = 150
                    self.err_msg = 'Invalid app meta data, meta data is not in valid JSON file'
                    logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                if self.validateMandatoryFields("app.json",callType,appState) != 0:
                    raise Exception()
                    return self.err_code, self.err_msg
                # append media information
                self.appMeta["iconfile"] = "/UIAssets/" + self.appMeta["iconfile"]
                self.appMeta["media"] = {}
                self.appMeta["media"]["readme"] = glob.glob("Readme/*")
                self.appMeta["media"]["license"] = glob.glob("License/*")
                self.appMeta["media"]["introvideo"] = glob.glob("IntroVideo/*")
                self.appMeta["media"]["snapshots"] = glob.glob("Snapshots/*")
                self.appMeta["media"]["release-notes"] = glob.glob("ReleaseNotes/*")
            else:
                try:
                    extracted_path=os.path.join(str(self.appExtractLoc))
                    subdir=str(next(os.walk(extracted_path))[1])
                    size=len(subdir)-2
                    subdir1=subdir[2:size]
                    json_path=extracted_path+"/"+subdir1+"/"+'app.json'
                    self.appMeta = json.load(open(json_path, 'r'))
                    self.appMeta["signature"]=""
                except Exception as e:
                    if len(str(e)):
                        logger.error(str(e))
                    self.err_code = 150
                    self.err_msg = 'Invalid app meta data, meta data is not in valid JSON file'
                    logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
                    return self.err_code, self.err_msg
                   # append media information
                temp=os.path.join(str(self.appExtractLoc))
                json_path=temp+"/"+subdir1+"/app.json"
                logger.info('Checking if mandatory fields exist in app.json')
                if self.validateMandatoryFields(json_path,callType,appState) != 0:
                    raise Exception()
                    return self.err_code, self.err_msg
                logger.info('Mandatory fields check successful')
                self.appMeta["iconfile"] =  str(self.appExtractLoc)+ "/"+subdir1+"/UIAssets/" + self.appMeta["iconfile"]
                self.appMeta["media"] = {}
                self.appMeta["media"]["readme"] = glob.glob(str(self.appExtractLoc) + "/"+subdir1+"/Media/Readme/*")
                self.appMeta["media"]["license"] = glob.glob(str(self.appExtractLoc) + "/"+subdir1+"/Media/License/*")
                self.appMeta["media"]["introvideo"] = glob.glob(str(self.appExtractLoc) +"/"+subdir1+"/Media/IntroVideo/*")
                self.appMeta["media"]["snapshots"] = glob.glob(str(self.appExtractLoc) + "/"+subdir1+"/Media/Snapshots/*")
                self.appMeta["media"]["release-notes"] = glob.glob(str(self.appExtractLoc) + "/"+subdir1+"/Media/ReleaseNotes/*")
                if self.publicKeyPath is not None:
                    signature_filename=temp+"/"+subdir1+".dev.signature"
                    if os.path.exists(signature_filename) == True:
                        self.appMeta["signature"] = open(signature_filename, "r").read()
                    else:
                        self.err_code = 150
                        self.err_msg = 'Missing developer signature file {0}'.format(signature_filename)
                        raise Exception()
                        return self.err_code, self.err_msg
        logger.info('Meta data retrieved successfully')
        return 0, ''

    def validateAuthor(self,callType):
        logger.info('Validating author')
        author=self.appMeta["author"]
        author=author.strip()
        size_author=len(author)
        if size_author<=0 or size_author>256:
            self.err_code = 151
            self.err_msg = 'Invalid author, author should be between 1 and 256 characters'
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        logger.info('Author validation successful')
        return 0

    #validate fields inside api: mamimum length of field is 1024
    def validateAppApis(self,callType,appState):
        logger.info('Validating app api')
        for key,value in self.appMeta["api"].items():
            key=key.strip()
            size_key=len(key)
            if size_key<=0 or size_key>256:
                self.err_code = 152
                self.err_msg = 'Invalid api, api should be between 1 and 256 characters'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
            check_alnum=key.isalnum()
            if check_alnum == False:
                self.err_code = 153
                self.err_msg = 'Invalid api, api should be alphanumeric'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
            value=value.strip()
            size_value=len(value)
            if size_value<=0 or size_value>1024:
                self.err_code = 154
                self.err_msg = 'Invalid api description, description should be between 1 and 1024 characters'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
        logger.info('App api validation successful')
        return 0

    # validate fields inside permission
    def validateAppPermissions(self,callType,appState):
        logger.info('Validating app permission')
        allowed_permissions=["admin", "access-connectivity-l1","access-connectivity-l2","access-connectivity-l3","access-connectivity-mgmt","access-connectivity-util","access-equipment","access-protocol-l1","access-protocol-l2","access-protocol-l3","access-protocol-mgmt","access-protocol-ops","access-protocol-util","access-qos","fabric-connectivity-l1","fabric-connectivity-l2","fabric-connectivity-l3","fabric-connectivity-mgmt","fabric-connectivity-util","fabric-equipment","fabric-protocol-l1","fabric-protocol-l2","fabric-protocol-l3","fabric-protocol-mgmt","fabric-protocol-ops","fabric-protocol-util","nw-svc-device","nw-svc-devshare","nw-svc-policy","ops","tenant-connectivity-l1","tenant-connectivity-l2","tenant-connectivity-l3","tenant-connectivity-mgmt","tenant-connectivity-util","tenant-epg","tenant-ext-connectivity-l1","tenant-ext-connectivity-l2","tenant-ext-connectivity-l3","tenant-ext-connectivity-mgmt","tenant-ext-connectivity-util","tenant-ext-protocol-l1","tenant-ext-protocol-l2","tenant-ext-protocol-l3","tenant-ext-protocol-mgmt","tenant-ext-protocol-util","tenant-network-profile","tenant-protocol-l1","tenant-protocol-l2","tenant-protocol-l3","tenant-protocol-mgmt","tenant-protocol-ops","tenant-protocol-util","tenant-qos","tenant-security","vmm-connectivity","vmm-ep","vmm-policy","vmm-protocol-ops","vmm-security"]
        app_permissions=self.appMeta["permissions"]
        if not len(app_permissions):
            self.err_code = 155
            self.err_msg = 'Invalid permissions, permissions should not be empty'
            logger.error('Error occurred: %d %s'%(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if len(app_permissions) != len(set(app_permissions)):
            self.err_code = 156
            self.err_msg = 'Invalid permissions, permissions has duplicate entries'
            logger.error('Error occurred: %d %s'%(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if not set(app_permissions).issubset(set(allowed_permissions)):
            diff = set(app_permissions).difference(set(allowed_permissions))
            self.err_code = 157
            self.err_msg = 'Invalid permissions, following permissions are not allowed - {0}'.format(', '.join(diff))
            logger.error('Error occurred: %d %s'%(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        logger.info('App permission validation successful')
        return 0

    def validateCategory(self,callType):
        logger.info('Validating category')
        allowed_category=["Tools and Utilities","Visibility and Monitoring","Optimization","Security","Networking","Cisco Automation and Orchestration"]
        app_category=self.appMeta["category"]
        if not len(app_category):
            self.err_code = 158
            self.err_msg = 'Invalid category, category should not be empty'
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if len(app_category) != len(set(app_category)):
            self.err_code = 159
            self.err_msg = 'Invalid category, category has duplicate entries'
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if not set(app_category).issubset(set(allowed_category)):
            diff = set(app_category).difference(set(allowed_category))
            self.err_code = 160
            self.err_msg = 'Invalid category, following categories are not allowed - {0}'.format(', '.join(diff))
            logger.error('Error occurred: %d %s'%(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        logger.info('Category validation successful')
        return 0

    # Validate fields in "contact"
    def validateAppContact(self,callType):
        logger.info('Validating contact fields')
        email=str(self.appMeta["contact"]["contact-email"])
        phone=str(self.appMeta["contact"]['contact-phone'])
        url=str(self.appMeta["contact"]["contact-url"])

        '''
        # Validate contact-url
        url=url.strip()
        if(len(url)>0):
            #check if URL value matches URL format i.e http://www.xyz.somedomain or http://xyz.somedomain
            urlValidationResult = validators.url(url)
            if(str(urlValidationResult) != "True"):
                self.err_code = 161
                self.err_msg = 'Invalid contact-url'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code

        # Validate contact-email
        email=email.strip()
        if(len(email)>0):
            emailValidationResult=validators.email(email)
            if(str(emailValidationResult) != "True"):
                self.err_code = 162
                self.err_msg = 'Invalid contact-email'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code

        # Validate contact-phone matches phone format ###-#######
        invalid=False
        phone=phone.strip()
        if '-' not in phone:
            invalid=True
        else:
            s1=phone.split("-")
            if len(s1) != 2:
                invalid=True
            else:
                if len(s1[0])!=3 and len(s1[1])!=7:
                    invalid=True
                if not s1[0].isdigit():
                    invalid=True
                if not s1[1].isdigit():
                    invalid=True
        if invalid:
            self.err_code = 163
            self.err_msg = 'Invalid contact-phone, valid phone number format is 123-4567890'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        '''

        logger.info('Contact fields validation successful')
        return 0

    # Validate appid max 32 byte alphanumeric
    def validateAppId(self,callType):
        logger.info('Validating appid')
        self.appId=self.appMeta["appid"]
        self.appId=self.appId.strip()
        if len(self.appId)<=0 or len(self.appId)>32:
            self.err_code = 164
            self.err_msg = 'Invalid appid, appid should be between 1 and 32 characters'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        else:
            check_alnum=self.appId.isalnum()
            if check_alnum == False:
                self.err_code = 165
                self.err_msg = 'Invalid appid, appid should be alphanumeric'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
        logger.info('Appid validation successful')
        return 0

    # Validate vendordomain max 32 byte alphanumeric
    def validateVendorDomain(self,callType):
        logger.info('Validating vendordomain')
        self.vendorDomain=self.appMeta["vendordomain"]
        self.vendorDomain=self.vendorDomain.strip()
        if len(self.vendorDomain)<=0 or len(self.vendorDomain)>32:
            self.err_code = 166
            self.err_msg = 'Invalid vendordomain, vendordomain should be between 1 and 32 characters'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        else:
            check_alnum=self.vendorDomain.isalnum()
            if check_alnum == False:
                self.err_code = 167
                self.err_msg = 'Invalid vendordomain, vendordomain should be alphanumeric'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
        logger.info('Vendordomain validation successful')
        return 0

    # Validate app version
    def validateAppVersion(self,version,versionType,callType):
        if versionType == 'app':
            logger.info('Validating app version')
            max = 9999
        else:
            max = 999
        invalid=False
        version=version.strip()
        try:
            if '.' not in version:
                invalid=True
            else:
                split_version_list=version.split(".")
                if len(split_version_list) != 2:
                    invalid=True
                else:
                    major=int(split_version_list[0])
                    minor=int(split_version_list[1])
                    if major < 0 or major > max:
                        invalid=True
                    if minor < 0 or minor > max:
                        invalid=True
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            invalid=True
        if invalid:
            if versionType == 'app':
                self.err_code = 168
                self.err_msg = 'Invalid app version, version should be major.minor, where 0 <= major,minor <= {0}'.format(max)
            else:
                self.err_code = 169
                self.err_msg = 'Invalid apic version, version should be major.minor(mp), where m=maintenance and p=patch, and 0 <= major,minor,maintenance <= {0}'.format(max)
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        if versionType == 'app':
            logger.info('App version validation successful')
        return 0

    # Validate apic version
    def validateAPICVersion(self,callType):
        logger.info('Validating apic version')
        invalid=False
        apicVersion=str(self.appMeta["apicversion"])
        apicVersion=apicVersion.strip()
        try:
            if '(' not in apicVersion:
                invalid=True
            else:
                split1=apicVersion.split("(")[0]
                split2=apicVersion.split("(")[1].split(')')[0]
                if self.validateAppVersion(split1,'apic',callType) != 0:
                    invalid=True
                maintenance = split2[:-1]
                patch = split2[-1]
                if not patch.isalpha():
                    invalid=True
                if not patch.islower():
                    invalid=True
                if not maintenance.isdigit():
                    invalid=True
                maintenance = int(maintenance)
                if maintenance < 0 or maintenance > 999:
                    invalid=True
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            invalid=True

        if invalid:
            self.err_code = 169
            self.err_msg = 'Invalid apic version, version should be major.minor(mp), where m=maintenance and p=patch, and 0 <= major,minor,maintenance <= 999'
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code

        if callType != 'apic':
            logger.info('Apic version validation successful')
            return 0

        # When validating on apic also verify for supported apic version
        app_apic_version = apicVersion
        app_apic_major_version = app_apic_version.split('(')[0]
        app_apic_minor_version = app_apic_version.split('(')[1].split(')')[0]
        app_apic_major = int(app_apic_major_version.split('.')[0])
        app_apic_minor = int(app_apic_major_version.split('.')[1])
        if app_apic_minor_version.isdigit():
            app_apic_maint = int(app_apic_minor_version)
            app_apic_patch = ''
        else:
            app_apic_maint = int(app_apic_minor_version[:-1])
            app_apic_patch = app_apic_minor_version[-1]

        rc=commands.getstatusoutput('acidiag version')
        if rc[0]:
            self.err_code = 170
            self.err_msg = 'Error getting apic version using acidiag command'
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        else:
            actual_apic_version = rc[1].strip()

        # logger.info('app:{0}, apic:{1}'.format(app_apic_version, actual_apic_version))
        actual_apic_version_list = actual_apic_version.split('.')
        if len(actual_apic_version_list) == 4:
            actual_apic_major = int(actual_apic_version_list[0])
            actual_apic_minor = int(actual_apic_version_list[1])
            actual_apic_maint = int(actual_apic_version_list[2]) + 1
            actual_apic_patch = ''
        elif len(actual_apic_version_list) == 3:
            actual_apic_major = int(actual_apic_version_list[0])
            actual_apic_minor = int(actual_apic_version_list[1])
            if actual_apic_version_list[2].isdigit():
                actual_apic_maint = int(actual_apic_version_list[2])
                actual_apic_patch = ''
            else:
                actual_apic_maint = int(actual_apic_version_list[2][:-1])
                actual_apic_patch = actual_apic_version_list[2][-1]
        else:
            self.err_code = 171
            self.err_msg = 'Invalid apic version: {0}'.format(actual_apic_version)
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code

        can_app_run = True
        if app_apic_major > actual_apic_major:
            can_app_run = False
        elif app_apic_major == actual_apic_major:
            if app_apic_minor > actual_apic_minor:
                can_app_run = False
            elif app_apic_minor == actual_apic_minor:
                if app_apic_maint > actual_apic_maint:
                    can_app_run = False
                elif app_apic_maint == actual_apic_maint:
                    if actual_apic_patch != '' and app_apic_patch > actual_apic_patch:
                        can_app_run = False

        if not can_app_run:
            logger.error('app apic version:{0}, actual apic version:{1}'.format(app_apic_version, actual_apic_version))
            self.err_code = 172
            self.err_msg = 'Unsupported apic version'
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code


        logger.info('Apic version validation successful')
        return 0

    #validate iconfile field
    def validateIconFile(self,callType):
        logger.info('Validating icon file')
        import imghdr
        try:
            filename=str(self.appMeta["iconfile"])
            filename=filename.strip()
            name=filename.split('/')[-1]
            lName=len(name)
            if lName<=0 or lName>256:
                self.err_code = 173
                self.err_msg = 'Invalid iconfile, iconfile should be between 1 and 256 characters'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
            if self.UT == True:
                logger.info('Icon file validation successful')
                return 0
            if not os.path.isfile(filename):
                self.err_code = 174
                self.err_msg = 'Invalid iconfile, iconfile {0} does not exist'.format(filename)
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
            if imghdr.what(filename) != 'jpeg' and imghdr.what(filename) != 'png':
                self.err_code = 175
                self.err_msg = 'Invalid iconfile, iconfile should be a valid jpeg or png file'
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
                return self.err_code
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            return self.err_code
        logger.info('Icon file validation successful')
        return 0

    # Validate app name
    def validateAppName(self,callType):
        logger.info('Validating app Name')
        appname=self.appMeta["name"]
        appname=appname.strip()
        lName=len(appname)
        if lName<=0 or lName>256:
            self.err_code = 176
            self.err_msg = 'Invalid app name, app name should be between 1 and 256 characters'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        logger.info('App name validation successful')
        return 0

    # Validate short description
    def validateShortDescription(self,callType):
        logger.info('Validating short description')
        descr=str(self.appMeta["shortdescr"])
        descr=descr.strip()
        lName=len(descr)
        if lName<=0 or lName>1024:
            self.err_code = 177
            self.err_msg = 'Invalid short description, description should be between 1 and 1024 characters'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        logger.info('Short description validation successful')
        return 0

    # Validate app vendor
    def validateAppVendor(self,callType):
        logger.info('Validating app vendor')
        vendor=str(self.appMeta["vendor"])
        vendor=vendor.strip()
        lName=len(vendor)
        if lName<=0 or lName>256:
            self.err_code = 178
            self.err_msg = 'Invalid vendor, vendor name should be between 1 and 256 characters'
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        logger.info('App vendor validation successful')
        return 0

    def getFileType(self,type):
        if type==1:
            correctlast4characters=".txt"
        elif type==2:
            correctlast4characters=".png/.jpg"
        elif type==3:
            correctlast4characters=".mp4"
        return correctlast4characters

    def getFileNameSize1(self,mediaType,type,callType):
        retrievedLast4Characters=str(mediaType)[-6:-2]
        split1=str(mediaType).split("/")[-1:]
        split2=str(split1).split(".")[-2:]
        s3=len(split2[0])-2
        if( s3>256 ):
            self.err_code = 191
            self.err_msg = "File names should have maximum 256 characters"
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
        correctlast4characters=self.getFileType(type)
        if(len(correctlast4characters)>4):
            split_correctchar=correctlast4characters.split("/")
            if((split_correctchar[0] != retrievedLast4Characters) and (split_correctchar[1] != retrievedLast4Characters)):
                self.err_code = 192
                self.err_msg = str(mediaType)+" should be of type "+correctlast4characters
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
        else:
            if(correctlast4characters != retrievedLast4Characters):
                self.err_code = 192
                self.err_msg = str(mediaType)+" should be of type "+correctlast4characters
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)

    def getFileNameSize2(self,mediaType,type,max,callType):
        temp2=str(mediaType).split(",")
        mediaFiles=" "
        temp=0
        for i in temp2:
            temp=temp+1
            split1=i.split("/")[-1:]
            split2=str(split1).split(".")
            size=len(split2[0])-2
            if( size>256 ):
                self.err_code = 191
                self.err_msg = "File names should have maximum 256 characters"
                logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                self.exception_type(callType,self.err_code,self.err_msg)
            if(temp==max):
                retrievedLast4Characters=i[-6:-2]
            else:
                retrievedLast4Characters=i[-5:-1]
            correctlast4characters=self.getFileType(type)
            if(len(correctlast4characters)>4):
                split_correctchar=correctlast4characters.split("/")
                if((split_correctchar[0] != retrievedLast4Characters) and (split_correctchar[1] != retrievedLast4Characters)):
                    self.err_code = 192
                    self.err_msg = str(i)+" should be of type "+correctlast4characters
                    logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)
            else:
                if(correctlast4characters != retrievedLast4Characters):
                    self.err_code = 192
                    self.err_msg = str(i)+" should be of type "+correctlast4characters
                    logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    self.exception_type(callType,self.err_code,self.err_msg)

    def getSize(self,size,media,type,callType):
        if size==1:
            self.getFileNameSize1(media,type,callType)
        if size==0:
            pass
        if size>1:
            self.getFileNameSize2(media,type,size,callType)

    #validate media field
    def validateMedia(self,callType):
        logger.info('Validating app media files')
        try:
            str(self.appMeta["media"]["readme"]).decode('ascii')
            str(self.appMeta["media"]["license"]).decode('ascii')
            str(self.appMeta["media"]["release-notes"]).decode('ascii')
        except UnicodeDecodeError:
            self.err_code = 190
            self.err_msg = "readme.txt , license.txt and release-notes.txt should be ASCII"
            logger.info('Error occurred: %d %s' %(self.err_code, self.err_msg))
            self.exception_type(callType,self.err_code,self.err_msg)
            return self.err_code
        s1=len((self.appMeta["media"]["readme"]))
        self.getSize(s1,self.appMeta["media"]["readme"],1,callType)
        s1=len((self.appMeta["media"]["license"]))
        self.getSize(s1,self.appMeta["media"]["license"],1,callType)
        s1=len((self.appMeta["media"]["release-notes"]))
        self.getSize(s1,self.appMeta["media"]["release-notes"],1,callType)
        s1=len((self.appMeta["media"]["snapshots"]))
        self.getSize(s1,self.appMeta["media"]["snapshots"],2,callType)
        s1=len((self.appMeta["media"]["introvideo"]))
        self.getSize(s1,self.appMeta["media"]["introvideo"],3,callType)
        logger.info('App media files validation successful')
        return 0

    def release(self):
            self.appExtractLoc.release()

    def validateAppMetaData(self, callType, appState):
        logger.info('Validating app meta data')
        if self.validateAuthor(callType) != 0:
            return self.err_code, self.err_msg
        if self.validateCategory(callType) != 0:
            return self.err_code, self.err_msg
        if self.validateAppId(callType) != 0:
            return self.err_code, self.err_msg
        if self.validateAppVersion(str(self.appMeta["version"]),'app',callType) != 0:
            return self.err_code, self.err_msg
        if self.validateIconFile(callType) != 0:
            return self.err_code, self.err_msg
        if self.validateAppName(callType) != 0:
            return self.err_code, self.err_msg
        if self.validateShortDescription(callType) != 0:
            return self.err_code, self.err_msg
        if self.validateAppVendor(callType) != 0:
            return self.err_code, self.err_msg
        if self.validateMedia(callType) != 0:
            return self.err_code, self.err_msg
        if self.validateAPICVersion(callType) != 0:
            return self.err_code, self.err_msg
        if contactFieldPresent and self.validateAppContact(callType) != 0:
            return self.err_code, self.err_msg
        if appState == "stateful" and apiFieldPresent and self.validateAppApis(callType,appState) != 0:
            return self.err_code, self.err_msg
        if self.validateAppPermissions(callType,appState) != 0:
            return self.err_code, self.err_msg
        if self.validateVendorDomain(callType) != 0:
            return self.err_code, self.err_msg
        logger.info('Validating app meta data successful')
        return 0, ''

    # Unit test purpose only
    def unitTest(self):
        try:
            self.UT = True
            rc, msg = self.getAppMetaData("dummy","website",unitTestAppState,isUnitTest=True)
            if rc != 0:
                raise Exception()
            rc, msg = self.validateAppMetaData("website",unitTestAppState)
            if rc != 0:
                raise Exception()
            self.err_code = 0
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            logger.error('Validation failed for test file')

        # Return result
        return self.getResult()

    def main(self, filename, sourceDir, outputDir, publicKeyPath):
        try:
            self.appFilename = filename
            self.sourceDir = sourceDir
            self.outputDir = outputDir
            self.publicKeyPath=publicKeyPath

            if self.appFilename is None or self.appFilename == '':
                self.err_code = 1
                self.err_msg = "URL parameter filename is required and cannot be empty"
                raise Exception()

            if self.sourceDir is None or self.sourceDir == '':
                self.err_code = 2
                self.err_msg = "URL parameter outputDir is required and cannot be empty"
                raise Exception()

            if self.outputDir is None or self.outputDir == '':
                self.err_code = 3
                self.err_msg = "URL parameter sourceDir is required and cannot be empty"
                raise Exception()

            logger.info('Filename: %s' %(self.appFilename))
            logger.info('Output Directory: %s' %(self.outputDir))
            logger.info('Source Directory: %s' %(self.sourceDir))

            filename = self.sourceDir + '/' + self.appFilename
            logger.info('Validating file: %s' % (filename))

            if os.path.isfile(filename)==False:
                self.err_code = 4
                self.err_msg = '{0} does not exist'.format(filename)
                raise Exception()

            if os.path.isdir(self.sourceDir)==False:
                self.err_code = 5
                self.err_msg = 'Source directory {0} does not exist'.format(self.sourceDir)
                raise Exception()

            if os.path.isdir(self.outputDir)==False:
                self.err_code = 6
                self.err_msg = 'Output directory {0} does not exist'.format(self.outputDir)
                raise Exception()

            # Extract app files and get app state
            logger.info('Extracting input file')
            if self.extractFiles(filename,self.outputDir) != 0:
                raise Exception()
            logger.info('File extraction successful')
            subdir=str(next(os.walk(str(self.appExtractLoc)))[1])
            size=len(subdir)-2
            subdir1=subdir[2:size]
            appFolder=str(self.appExtractLoc)+"/"+subdir1+"/"
            extractedAppState=self.get_State(appFolder)
            logger.info('App state is: {0}'.format(extractedAppState))

            # Verify app signature if public key is provided
            if self.publicKeyPath is not None:
                if os.path.isfile(self.publicKeyPath)==False:
                    self.err_code = 7
                    self.err_msg = "Public key file {0} not found".format(self.publicKeyPath)
                    logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))
                    raise Exception()
                public_key_type=self.publicKeyPath[-4:]
                if (public_key_type==".pem"):
                    logger.info('Verifying signature')
                    if self.validateSignature(str(self.appExtractLoc)) != 0:
                        raise Exception()
                else:
                    self.err_code = 8
                    self.err_msg = "Public key file shoud be of type .pem"
                    raise Exception()

            # Validate app file, meta and directory structure
            if self.mandatoryFileCheck(filename,self.outputDir) != 0:
                raise Exception()
            rc, msg = self.getAppMetaData(filename,"website",extractedAppState,isUnitTest=False)
            if rc != 0:
                raise Exception()
            rc, msg = self.validateAppMetaData("website",extractedAppState)
            if rc != 0:
                raise Exception()

            self.appMeta['appid']=self.appMeta['vendordomain']+"_"+self.appMeta['appid']
            self.err_code = 0
        except Exception as e:
            if len(str(e)):
                logger.error(str(e))
            if self.err_msg == '':
                self.err_msg = str(e)
            logger.error('Error occurred: %d %s' %(self.err_code, self.err_msg))

        # Return result
        return self.getResult()

    @staticmethod
    def validateJsonFields(json_dict):
        logger.info('Validating JSON fields')
        callType = 'apic'
        validator = Validator()
        validator.appMeta = json_dict
        validator.UT = True
        if validator.validateAppId(callType) != 0:
            return validator.err_code, validator.err_msg
        if validator.validateAppVersion(str(validator.appMeta["version"]),'app',callType) != 0:
            return validator.err_code, validator.err_msg
        if validator.validateShortDescription(callType) != 0:
            return validator.err_code, validator.err_msg
        if validator.validateAppVendor(callType) != 0:
            return validator.err_code, validator.err_msg
        if validator.validateAPICVersion(callType) != 0:
            return validator.err_code, validator.err_msg
        if validator.validateVendorDomain(callType) != 0:
            return validator.err_code, validator.err_msg
        logger.info('Validating JSON fields successful')
        return 0, ''
