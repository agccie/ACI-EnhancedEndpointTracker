#!/usr/bin/python
# some problems with pexpect 4.4 - 4.2 works nicely

import time, string, pexpect, re
import subprocess
import logging

# module level logging
logger = logging.getLogger(__name__)

class Connection(object):
    """
    Object built primarily for executing commands on Cisco IOS/NXOS devices.
    The following methods and variables are available for use in this class:

        username         (opt) username credential (default 'admin')
        password         (opt) password credential (default 'cisco')
        enable_password  (opt) enable password credential (IOS only) 
        protocol         (opt) telnet/ssh option (default 'ssh')
        port             (opt) port to connect
                                (if different from telnet/ssh default)
        timeout          (opt) wait in seconds between each command (default 30)
        prompt           (opt) prompt to expect after each command 
        log              (opt) logfile (default None)
        verify           (opt) verify/enforce strictHostKey values for SSL 
                                (disabled by default)
        searchwindowsize (opt) maximum amount of data used in matching 
                                expressions. Extremely important to set to a 
                                low value for large outputs.
                                setting this class default=256
        force_wait       (opt) some OS ignore searchwindowsize and therefore 
                                still experience high CPU and long wait time 
                                for commands with large outputs to complete.
                                A workaround is to sleep the script instead of 
                                running regex checking for prompt character.
                                This is not generally needed...
                                Default is 0 seconds (disabled).  
                                If needed, a value of 8 is fairly reliable

    Example using all defaults
        c = Connection("10.122.140.89")
        c.cmd("show version")
        print "version of code: %s" % c.output

    @author agossett@cisco.com
    @version 07/28/2014
    """

    def __init__(self, hostname):
        self.hostname           = hostname
        self.log                = None
        self.username           = 'admin'
        self.password           = 'cisco'
        self.enable_password    = 'cisco'
        self.protocol           = "ssh"
        self.port               = None
        self.timeout            = 30
        self.prompt             = "[^#]#[ ]*(\x1b[\x5b-\x5f][\x40-\x7e])*[ ]*$"
        self.verify             = False
        self.searchwindowsize   = 256
        self.force_wait         = 0
        self.child              = None
        self.output             = ""    # output from last command
        self._term_len          = 0     # terminal length for cisco devices
        self._login             = False # set to true at first successful login
        self._log               = None  # variable for tracking logfile state
        self.bind               = None  # bind IP for ssh 

    def __connected(self):
        # determine if a connection is already open
        connected = (self.child is not None and self.child.isatty())
        logger.debug("check for valid connection: %r", connected)
        return connected

    @property
    def term_len(self): return self._term_len 

    @term_len.setter
    def term_len(self, term_len):
        self._term_len = int(term_len)
        if (not self.__connected()) or (not self._login):
            # login function will set the terminal length
            self.login()
        else:
            # user changing terminal length during operation, need to explicitly
            self.cmd("terminal length %s" % self._term_len)

    def start_log(self):
        """ start or restart sending output to logfile """
        if self.log is not None and self._log is None:
            # if self.log is a string, then attempt to open file pointer 
            # NOTE - don't catch exception, we want it to die if on error
            if isinstance(self.log, str) or isinstance(self.log, unicode):
                self._log = file(self.log, "a")
            else:
                self._log = self.log
            logger.debug("setting logfile to %s", self._log.name)
            if self.child is not None:
                self.child.logfile = self._log

    def stop_log(self):
        """ stop sending output to logfile """
        self.child.logfile = None
        self._log = None
        return

    def connect(self):
        # close any currently open connections
        self.close()

        # determine port if not explicitly set
        if self.port is None:
            if self.protocol == "ssh":
                self.port = 22
            if self.protocol == "telnet":
                self.port = 23
        # spawn new thread
        if self.protocol.lower() == "ssh":
            logger.debug("spawning new pexpect connection: ssh %s@%s -p %d", 
                self.username, self.hostname, self.port)
            no_verify = " -o StrictHostKeyChecking=no -o LogLevel=ERROR "
            no_verify+= " -o UserKnownHostsFile=/dev/null"
            no_verify+= " -o HostKeyAlgorithms=+ssh-dss"
            no_verify+= " -c aes128-ctr,aes256-ctr,aes192-ctr,aes128-cbc,3des-cbc,aes192-cbc,aes256-cbc"
            if self.verify: no_verify = ""
            if self.bind is not None: no_verify = " -b %s" % self.bind
            self.child = pexpect.spawn("ssh %s %s@%s -p %d" % (no_verify, 
                self.username, self.hostname, self.port),
                searchwindowsize = self.searchwindowsize)
        elif self.protocol.lower() == "telnet":
            logger.info("spawning new pexpect connection: telnet %s %d", 
                self.hostname, self.port)
            self.child = pexpect.spawn("telnet %s %d"%(self.hostname,self.port),
                searchwindowsize = self.searchwindowsize)
        # support custom protocols such as vsh/vsh_lc
        else:
            logger.info("custom protocol spawn: %s", self.protocol)
            self.child = pexpect.spawn("%s" % self.protocol)

        # start logging
        self.start_log()

    def close(self):
        # try to gracefully close the connection if opened
        if self.__connected():
            logger.info("closing current connection")
            self.child.close()
        self.child = None
        self._login = False

    def __expect(self, matches, timeout=None):
        """
        receives a dictionary 'matches' and returns the name of the matched item
        instead of relying on the index into a list of matches.  Automatically
        adds following options if not already present
            "eof"       : pexpect.EOF
            "timeout"   : pexpect.TIMEOUT
        """

        if "eof" not in matches:
            matches["eof"] = pexpect.EOF
        if "timeout" not in matches:
            matches["timeout"] = pexpect.TIMEOUT

        if timeout is None: timeout = self.timeout
        indexed = []
        mapping = []
        for i in matches:
            indexed.append(matches[i])
            mapping.append(i)
        result = self.child.expect(indexed, timeout)
        logger.debug("timeout: %d, matched: '%s'\npexpect output: '%s%s'",
            timeout, self.child.after, self.child.before, self.child.after)
        if result <= len(mapping) and result>=0:
            logger.debug("expect matched result[%d] = %s",
                result, mapping[result])
            return mapping[result]
        ds = ''
        logger.error("unexpected pexpect return index: %s", result)
        for i in range(0,len(mapping)):
            ds+= '[%d] %s\n' % (i, mapping[i])
        logger.debug("mapping:\n%s", ds)
        raise Exception("Unexpected pexpect return index: %s" % result)

    def login(self, max_attempts=7, timeout=5):
        """
        returns true on successful login, else returns false
        """

        logger.debug("logging into host")

        # successfully logged in at a different time
        if not self.__connected():
            self.connect()
        # check for user provided 'prompt' which indicates successful login
        # else provide approriate username/password/enable_password
        matches = {
            "console"   : "(?i)press return to get started",
            "refuse"    : "(?i)connection refused",
            "yes/no"    : "(?i)yes/no",
            "username"  : "(?i)(user(name)*|login)[ as]*[ \t]*:[ \t]*$",
            "password"  : "(?i)password[ \t]*:[ \t]*$",
            "enable"    : ">[ \t]*$",
            "prompt"    : self.prompt
        }

        last_match = None
        while max_attempts>0:
            max_attempts-=1
            match = self.__expect(matches, timeout)
            if match == "console":      # press return to get started
                logger.debug("matched console, send enter")
                self.child.sendline("\r\n")
            elif match == "refuse":    # connection refused
                logger.error("connection refused by host")
                return False
            elif match == "yes/no":   # yes/no for SSH key acceptance
                logger.debug("received yes/no prompt, send yes")
                self.child.sendline("yes")
            elif match == "username":   # username/login prompt
                logger.debug("received username prompt, send username")
                self.child.sendline(self.username)
            elif match == "password":
                # don't log passwords to the logfile
                self.stop_log()
                if last_match == "enable":
                    # if last match was enable prompt, then send enable password
                    logger.debug("matched 'enable', send enable password")
                    self.child.sendline(self.enable_password)
                else:
                    logger.debug("matched 'password', send password")
                    self.child.sendline(self.password)
                # restart logging
                self.start_log()
            elif match == "enable":
                logger.debug("matched enable prompt, send enable")
                self.child.sendline("enable")
            elif match == "prompt":
                logger.debug("successful login")
                self._login = True
                return True
            elif match == "timeout":
                logger.debug("timeout received but connection still opened")
                self.child.sendline("\r\n")
            last_match = match
        # did not find prompt within max attempts, failed login
        logger.error("failed to login after multiple attempts")
        return False

    def remote_login(self, command, max_attempts=3, timeout=5):
        """ execute a remote ssh/telnet login command on an active connection
            object. This allows user to login to a device through a jump box.
        """
        if not self.__connected():
            self.connect()
        self.child.sendline(command)
        return self.login(max_attempts=max_attempts, timeout=timeout) 

    def cmd(self, command, **kwargs):
        """
        execute a command on a device and wait for one of the provided matches 
        to return.
        Required argument string command
        Optional arguments:
            timeout     seconds to wait for command to completed 
                        default: self.timeout
            sendline    boolean flag to use send or sendline fuction
                        default: True
            matches     dictionary of key/regex to match against. Key 
                        corresponding to matched regex will be returned. 
                        By default, the following three keys/regex are applied:
                            'eof'       : pexpect.EOF
                            'timeout'   : pexpect.TIMEOUT
                            'prompt'    : self.prompt
            echo_cmd    boolean flag to echo commands sent
                        note most terminals (i.e., Cisco devices) will echo 
                        back all typed characters by default. Therefore, 
                        enabling echo_cmd may cause duplicate cmd characters.
                        default: False
        Return:
        returns the key from the matched regex. 
        For most scenarios, this will be 'prompt'. The output from the command 
        can be collected from self.output variable
        """

        sendline = kwargs.get("sendline", True)
        timeout = kwargs.get("timeout", self.timeout)
        matches = kwargs.get("matches", {})
        echo_cmd = kwargs.get("echo_cmd", False) 

        # ensure prompt is in the matches list
        if "prompt" not in matches: matches["prompt"] = self.prompt

        self.output = ""
        # check if we've ever logged into device or currently connected
        if (not self.__connected()) or (not self._login):
            logger.debug("no active connection, attempt to login")
            if not self.login():
                raise Exception("failed to login to host")

        # if echo_cmd is disabled, then need to disable logging before
        # executing commands
        if not echo_cmd: self.stop_log()

        # execute command
        logger.debug("cmd command: %s", command)
        if sendline: self.child.sendline(command)
        else: self.child.send(command)

        # remember to re-enable logging
        if not echo_cmd: self.start_log()

        # force wait option
        if self.force_wait != 0:
            time.sleep(self.force_wait)

        result = self.__expect(matches, timeout)
        self.output = "%s%s" % (self.child.before, self.child.after)
        if result == "eof" or result == "timeout":
            logger.warn("unexpected %s occurred", result)
        return result

