#!/usr/bin/python

import time, string, pexpect, re
import subprocess
import logging

class Connection(object):
    """
    Object built primarily for executing commands on Cisco IOS/NXOS devices.  The following
    methods and variables are available for use in this class:
        Connection.username         (opt) username credential (default 'admin')
        Connection.password         (opt) password credential (default 'cisco')
        Connection.enable_password  (opt) enable password credential (IOS only) (default 'cisco')
        Connection.protocol         (opt) telnet/ssh option (default 'ssh')
        Connection.port             (opt) port to connect on (if different from telnet/ssh default)
        Connection.timeout          (opt) wait in seconds between each command (default 30)
        Connection.prompt           (opt) prompt to expect after each command (best practice - don't change)
        Connection.log              (opt) logfile (default None)
        Connection.verify           (opt) verify/enforce strictHostKey values for SSL (disabled by default)
        Connection.searchwindowsize (opt) maximum amount of data used in matching expressions
                                          extremely important to set to a low value for large outputs
                                          pexpect default = None, setting this class default=256
        Connection.force_wait       (opt) small OS ignore searchwindowsize and therefore still experience high
                                            CPU and long wait time for commands with large outputs to complete.
                                            A workaround is to sleep the script instead of running regex checking
                                            for prompt character.
                                            This should only be used in those unique scenarios...
                                            Default is 0 seconds (disabled).  If needed, set to 8 (seconds)

        Connection.debug_level()    (opt) set debugging level (default to Debug.INFO)
        Connection.connect()        (opt) connect to device with provided protocol/port/hostname
        Connection.login()          (opt) log into device with provided credentials
        Connection.close()          (opt) close current connection
        Connection.cmd()            execute a command on the device (provide matches and timeout)

    Example using all defaults
        c = Connection("10.122.140.89")
        c.cmd("terminal length 0")
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
        self.output             = ""        # output from last command
        self._term_len          = -1        # terminal length for cisco devices
        self._login             = False     # set to true at first successful login
        self._log               = None      # private variable for tracking logfile state

    def __connected(self):
        # determine if a connection is already open
        connected = (self.child is not None and self.child.isatty())
        logging.debug("check for valid connection: %r" % connected)
        return connected

    @property
    def term_len(self): return self._term_len 

    @term_len.setter
    def term_len(self, term_len):
        self._term_len = int(term_len)
        # don't issue term length when less than zero
        if self._term_len < 0: return
        if (not self.__connected()) or (not self._login):
            # login function will set the terminal length
            self.login()
        else:
            # user changing terminal length during operation, need to explicitly
            self.cmd("terminal length %s" % self._term_len)

    def start_log(self):
        """ start or restart sending output to logfile """
        if self.log is not None and self._log is None:
            # if self.log is a string, then attempt to open file pointer (do not catch exception, we want it
            # to die if there's an error opening the logfile)
            if isinstance(self.log, str) or isinstance(self.log, unicode):
                self._log = file(self.log, "a")
            else:
                self._log = self.log
            logging.debug("setting logfile to %s" % self._log.name)
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
            no_verify = " -o StrictHostKeyChecking=no -o LogLevel=ERROR -o UserKnownHostsFile=/dev/null"
            if self.verify: no_verify = ""
            logging.debug("spawning new pexpect connection: ssh %s %s@%s -p %d" % (no_verify, self.username, self.hostname, self.port))
            self.child = pexpect.spawn("ssh %s %s@%s -p %d" % (no_verify, self.username, self.hostname, self.port),
                searchwindowsize = self.searchwindowsize)
        elif self.protocol.lower() == "telnet":
            logging.info("spawning new pexpect connection: telnet %s %d" % (self.hostname, self.port))
            self.child = pexpect.spawn("telnet %s %d" % (self.hostname, self.port),
                searchwindowsize = self.searchwindowsize)
        else:
            logging.error("unknown protocol %s" % self.protocol)
            raise Exception("Unsupported protocol: %s" % self.protocol)

        # start logging
        self.start_log()

    def close(self):
        # try to gracefully close the connection if opened
        if self.__connected():
            logging.info("closing current connection")
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
        logging.debug("timeout: %d, matched: '%s'\npexpect output: '%s%s'" % (timeout, self.child.after, self.child.before, self.child.after))
        if result <= len(mapping) and result>=0:
            logging.debug("expect matched result[%d] = %s" % (result, mapping[result]))
            return mapping[result]
        ds = ''
        logging.error("unexpected pexpect return index: %s" % result)
        for i in range(0,len(mapping)):
            ds+= '[%d] %s\n' % (i, mapping[i])
        logging.debug("mapping:\n%s" % ds)
        raise Exception("Unexpected pexpect return index: %s" % result)

    def login(self, max_attempts=7, timeout=17):
        """
        returns true on successful login, else returns false
        """

        logging.debug("Logging into host")

        # successfully logged in at a different time
        if not self.__connected(): self.connect()
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
                logging.debug("matched console, send enter")
                self.child.sendline("\r\n")
            elif match == "refuse":    # connection refused
                logging.error("connection refused by host")
                return False
            elif match == "yes/no":   # yes/no for SSH key acceptance
                logging.debug("received yes/no prompt, send yes")
                self.child.sendline("yes")
            elif match == "username":   # username/login prompt
                logging.debug("received username prompt, send username")
                self.child.sendline(self.username)
            elif match == "password":
                # don't log passwords to the logfile
                self.stop_log()
                if last_match == "enable":
                    # if last match was enable prompt, then send enable password
                    logging.debug("matched password prompt, send enable password")
                    self.child.sendline(self.enable_password)
                else:
                    logging.debug("matched password prompt, send password")
                    self.child.sendline(self.password)
                # restart logging
                self.start_log()
            elif match == "enable":
                logging.debug("matched enable prompt, send enable")
                self.child.sendline("enable")
            elif match == "prompt":
                logging.debug("successful login")
                self._login = True
                # force terminal length at login
                self.term_len = self._term_len
                return True
            elif match == "timeout":
                logging.debug("timeout received but connection still opened, send enter")
                self.child.sendline("\r\n")
            last_match = match
        # did not find prompt within max attempts, failed login
        logging.error("failed to login after multiple attempts")
        return False

    def remote_login(self, command, **kwargs):
        """ when connecting through a device acting as a 'jump' server, 
            it's necessary to login to a remote device through the expect shell.
            This function accepts the login command and walks through normal
            login function.
            kwargs are passed from this function to login
            NOTE, if jump requires different credentials, calling function must
            change credentials before executing remote_login and then restore
            as needed after remote_login compeletes
        """

        # successfully logged in at a different time
        if not self.__connected(): self.connect()
        self.child.sendline(command)
        return self.login(**kwargs)       

    def cmd(self, command, **kargs):
        """
        execute a command on a device and wait for one of the provided matches to return.
        Required argument string command
        Optional arguments:
            timeout - seconds to wait for command to completed (default to self.timeout)
            sendline - boolean flag to use send or sendline fuction (default to true)
            matches - dictionary of key/regex to match against.  Key corresponding to matched
                regex will be returned.  By default, the following three keys/regex are applied:
                    'eof'       : pexpect.EOF
                    'timeout'   : pexpect.TIMEOUT
                    'prompt'    : self.prompt
            echo_cmd - boolean flag to echo commands sent (default to false)
                note most terminals (i.e., Cisco devices) will echo back all typed characters
                by default.  Therefore, there is enabling echo_cmd may cause duplicate cmd characters
        Return:
        returns the key from the matched regex.  For most scenarios, this will be 'prompt'.  The output
        from the command can be collected from self.output variable
        """

        sendline = True
        timeout = self.timeout
        matches = {}
        echo_cmd = False
        if "timeout" in kargs:
            timeout = kargs["timeout"]
        if "matches" in kargs:
            matches = kargs["matches"]
        if "sendline" in kargs:
            sendline = kargs["sendline"]
        if "echo_cmd" in kargs:
            echo_cmd = kargs["echo_cmd"]

        # ensure prompt is in the matches list
        if "prompt" not in matches:
            matches["prompt"] = self.prompt

        self.output = ""
        # check if we've ever logged into device or currently connected
        if (not self.__connected()) or (not self._login):
            logging.debug("no active connection, attempt to login")
            if not self.login():
                raise Exception("failed to login to host")

        # if echo_cmd is disabled, then need to disable logging before
        # executing commands
        if not echo_cmd: self.stop_log()

        # execute command
        logging.debug("cmd command: %s" % command)
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
            logging.warning("unexpected %s occurred" % result)
        return result

