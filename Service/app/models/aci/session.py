"""
    ACI session handler

    This heavily leverages the acitoolkit Session module:
    https://github.com/datacenter/acitoolkit
"""

from requests.exceptions import ConnectionError
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from six.moves.queue import Queue
from websocket import create_connection
from websocket import WebSocketException
from urllib import unquote
from OpenSSL.crypto import FILETYPE_PEM
from OpenSSL.crypto import load_privatekey
from OpenSSL.crypto import sign

import base64
import copy
import json
import logging
import re
import requests
import socket
import ssl
import threading
import time
import traceback
import urllib3

# module level logging
logger = logging.getLogger(__name__)

# disable urllib warnings
urllib3.disable_warnings()

class aaaUserDomain(object):
    """ track read and write for aaaUserDomain info received at login """
    def __init__(self, name, read_roles, write_roles):
        self.name = name
        self.read_roles = read_roles
        self.write_roles = write_roles
    
    def __repr__(self):
        return "%s, read:[%s], write:[%s]" % (
                self.name,
                ",".join(self.read_roles),
                ",".join(self.write_roles)
            )


class Session(object):
    """ Session class responsible for all communication with the APIC """
    def __init__(self, url, uid, pwd=None, cert_name=None, key=None, verify_ssl=False,
                 appcenter_user=False, proxies=None, resubscribe=True):
        """
            url (str)               apic url such as https://1.2.3.4
            uid (str)               apic username or certificate name 
            pwd (str)               apic password
            cert_name (str)         certificate name for certificate-based authentication
            key (str)               path to certificate file used for certificate-based 
                                    authentication if a password is provided then it will be 
                                    prefered over certficate
            verify_ssl (bool)       verify ssl certificate for ssl connections
            appcenter_user (bool)   set to true when using certificate authentication from ACI app
            proxies (dict)          optional dict containing the proxies passed to request library
            resubscribe (bool)      auto resubscribe on if subscription or login fails
                                    if false then subscription thread is closed on refresh failure
        """
        if not isinstance(url, basestring): url = str(url)
        if not isinstance(uid, basestring): uid = str(uid)
        if pwd is not None and not isinstance(pwd, basestring): pwd = str(pwd)
        if key is not None and not isinstance(key, basestring): key = str(key)
        if pwd is None and (key is None or cert_name is None):
            raise Exception("A password or cert_name and key are required")

        r1 = re.search("^(?P<protocol>https?://)?(?P<hostname>.+$)", url.lower())
        if r1 is not None:
            self.hostname = r1.group("hostname")
            if r1.group("protocol") is None: 
                self.api = "https://%s" % self.hostname
            else:
                self.api = "%s%s" % (r1.group("protocol"), self.hostname)
        else:
            raise Exception("invalid APIC url: %s" % url)

        self.uid = uid
        self.pwd = pwd
        self.cert_name = cert_name
        self.key = key
        self.appcenter_user = appcenter_user
        self.default_timeout = 120
        self.resubscribe = resubscribe
        # indexed by aaaUserDomain name and contains all permission info discovered at login
        self.domains = {}               

        if self.pwd is not None:
            self.cert_auth = False
        else:
            self.cert_auth = True
            try:
                with open(self.key, 'r') as f:
                    self._x509Key = load_privatekey(FILETYPE_PEM, f.read())
            except Exception as e:
                logger.debug("Traceback:\n%s", traceback.format_exc())
                raise TypeError("Could not load private key(%s): %s" % (self.key, e))

        self.verify_ssl = verify_ssl
        self.session = None
        self.token = None
        self.login_thread = Login(self)
        self.subscription_thread = None
        self._logged_in = False
        self._proxies = proxies
        # Disable the warnings for SSL
        if not self.verify_ssl:
            requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    def _prep_x509_header(self, method, url, data=None):
        """ This function returns a dictionary containing the authentication signature for a given
            request based on the private key and certificate name given to the session object. If 
            the session object is using normal (user/pass) authentication an empty dictionary is 
            returned.

            To calculate the signature the request is calculated on a string with format:
            '<HTTP-METHOD><URL><PAYLOAD>'
            Note, the URL *does not* include the DNS/IP of the APIC
        """
        if not self.cert_auth:
            return {}
        # for appcenter_user, once a token is acquired and logged they are logged in,
        # no need to build x509 header since authentication is using token
        if self.appcenter_user and self._logged_in:
            return {}
        if not self.session:
            self.session = requests.Session()
        if self.appcenter_user:
            cert_dn = 'uni/userext/appuser-{0}/usercert-{1}'.format(self.uid, self.cert_name)
        else:
            cert_dn = 'uni/userext/user-{0}/usercert-{1}'.format(self.uid, self.cert_name)

        url = unquote(url)
        #logger.debug("Perparing cert, dn:%s, key:%s, request: %s %s, data: %s", cert_dn,
        #    self.key, method, url, data)
        payload = "%s%s" % (method, url)
        if data is not None:
            payload += data
        signature = base64.b64encode(sign(self._x509Key, payload, 'sha256'))
        cookie = {
            'APIC-Request-Signature': signature,
            'APIC-Certificate-Algorithm': 'v1.0',
            'APIC-Certificate-Fingerprint': 'fingerprint',
            'APIC-Certificate-DN': cert_dn
        }
        #logger.debug('Authentication cookie %s', cookie)
        return cookie

    def _send_login(self, timeout=None):
        """ send the actual login request to the APIC and open the web socket interface. """

        self._logged_in = False
        self.session = requests.Session()

        if self.appcenter_user:
            login_url = '/api/requestAppToken.json'
            data = {'aaaAppToken':{'attributes':{'appName': self.cert_name}}}
        elif self.cert_auth:
            # skip login for non appcenter_user cert auth
            resp = requests.Response()
            resp.status_code = 200
            return resp
        else:
            login_url = '/api/aaaLogin.json'
            data = {'aaaUser': {'attributes': {'name': self.uid, 'pwd': self.pwd}}}
        ret = self.push_to_apic(login_url, data=data, timeout=timeout, retry=False)
        if not ret.ok:
            logger.warn("could not login to apic, closing session")
            self.close()
            return ret
        self._logged_in = True
        ret_data = json.loads(ret.text)['imdata'][0]
        timeout = ret_data['aaaLogin']['attributes']['refreshTimeoutSeconds']
        self.token = str(ret_data['aaaLogin']['attributes']['token'])
        self.login_thread._login_timeout = int(timeout) / 2
        # set domains from aaaUserDomain info
        self.domains = {}
        if 'children' in ret_data['aaaLogin'] and len(ret_data['aaaLogin']['children'])>0:
            for child in ret_data['aaaLogin']['children']:
                classname = child.keys()[0]
                if classname == 'aaaUserDomain':
                    logger.debug('adding aaaUserDomain to session domains: %s', child)
                    domain = child['aaaUserDomain']['attributes']
                    name = domain['name']
                    read_roles = []
                    write_roles = []
                    if 'rolesR' in domain:
                        read_roles = domain['rolesR'].split(',')
                    else:
                        logger.debug('unable to determine read role for domain %s', name)
                    if 'rolesW' in domain:
                        write_roles = domain['rolesW'].split(',')
                    else:
                        logger.debug('unable to determine write role for domain %s', name)
                    self.domains[name] = aaaUserDomain(name, read_roles, write_roles)
        return ret

    def push_to_apic(self, url, data={}, timeout=None, method="POST", retry=True):
        """ POST/DELETE the object data to the APIC

            url (str)       relative url to post/delete
            data (dict)     data to send to the APIC
            timeout (int)   timeout in seconds to complete the request
            method (str)    method (POST or DELETE)
            retry (bool)    retry post/delete on failure

            returns requests response object
        """
        return self._send(method, url, data=data, timeout=timeout, retry=retry)

    def get(self, url, timeout=None, retry=True):
        """ perform REST GET request to apic

            url (str)       relative url to get
            timeout (int)   timeout in seconds to complete the request
            retry (bool)    retry get on failure

            returns requests response object
        """
        return self._send("GET", url, timeout=timeout, retry=retry)


    def init_subscription_thread(self):
        """ start subscription thread """
        if self.subscription_thread is None:
            self.subscription_thread = Subscriber(self, resubscribe=self.resubscribe)
            self.subscription_thread.daemon = True
            self.subscription_thread.start()

    def subscribe(self, url, callback, only_new=True, paused=False):
        """ subscribe to events for a particular url, return bool success"""
        self.init_subscription_thread()
        return self.subscription_thread.subscribe(url, callback, only_new=only_new, paused=paused)

    def unsubscribe(self, url):
        """ unsubscribe from a particular url """
        if self.subscription_thread is not None:
            self.subscription_thread.unsubscribe(url)

    def login(self, timeout=30):
        """ login to APIC, return bool success """
        try:
            resp = self._send_login(timeout)
            if resp.status_code == 200:
                self.login_thread.daemon = True
                self.login_thread.start()
                return True
        except ConnectionError as e:
            logger.warn('Could not login to APIC due to ConnectionError: %s', e)
        return False

    def refresh_login(self, timeout=None):
        """ Refresh the login to the APIC, return bool success """
        logger.debug("refreshing apic login")
        refresh_url = '/api/aaaRefresh.json'
        resp = self.get(refresh_url, timeout=timeout, retry=False)
        if resp.status_code == 200:
            ret_data = json.loads(resp.text)['imdata'][0]
            self.token = str(ret_data['aaaLogin']['attributes']['token'])
            return True
        else:
            logger.debug("failed to refresh apic login")
            return False

    def close(self):
        """ Close the session """
        if self.login_thread is not None:
            self.login_thread.exit()
        if self.subscription_thread is not None:
            self.subscription_thread.exit()
        self.session.close()

    def _send(self, method, url, data=None, timeout=None, retry=True):
        """ perform GET/POST/DELETE request to apic
            returns requests response object
        """
        if method == "GET":
            session_method = self.session.get
        elif method == "POST":
            session_method = self.session.post
        elif method == "DELETE":
            session_method = self.session.delete
        else:
            raise Exception("unsupported http method %s (expect GET, POST, or DELETE)" % method)

        # if timeout is not set then use default
        if timeout is None:
            timeout = self.default_timeout

        # prep data and certificate before request
        if data is not None: data = json.dumps(data, sort_keys=True)
        cookies = self._prep_x509_header(method, url, data=data)

        url = "%s%s" % (self.api, url)
        #logger.debug("%s %s", method, url)
        # perform request method with optional retry
        resp = session_method(url, data=data, verify=self.verify_ssl, timeout=timeout, 
                    proxies=self._proxies, cookies=cookies)
        if resp.status_code == 403 and retry:
            logger.warn('%s, refreshing login and will try again', resp.text)
            resp = self._send_login()
            if resp.ok:
                resp = session_method(url, data=data, verify=self.verify_ssl, timeout=timeout, 
                        proxies=self._proxies, cookies=cookies)
            else:
                logger.warn('retry login failed')
        return resp

    def _resubscribe(self):
        """ resubscribe to current subscriptions 
            this is triggered by login thread on failed refresh 
            return bool success
        """
        if self.subscription_thread is not None:
            return self.subscription_thread._resubscribe()
        return True

class Login(threading.Thread):
    """ Login thread responsible for refreshing the APIC login before timeout """
    def __init__(self, session):
        threading.Thread.__init__(self)
        self._session = session
        self._login_timeout = 0
        self._exit = False

    def exit(self):
        """ Indicate that the thread should exit """
        logger.debug("exiting login thread")
        self._exit = True
        if self._session.subscription_thread is not None:
            self._session.subscription_thread.exit()

    def run(self):
        while not self._exit:
            time.sleep(self._login_timeout)
            refreshed = False
            try:
                logger.debug("refreshing session token")
                refreshed = self._session.refresh_login(timeout=30)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                logger.warn('connection error or timeout on login refresh')
                self._login_timeout = 30
            if not refreshed:
                try:
                    if not self._session._send_login().ok:
                        logger.warn("login failed, existing login thread")
                        return self.exit()
                    if not self._session._resubscribe():
                        logger.warn("failed to resubscribe to subscriptions, exiting login thread")
                        return self.exit()
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                    logger.warn('second connection error or timeout on login refresh')
                    return self.exit()
                except Exception as e:
                    logger.debug("Traceback:\n%s", traceback.format_exc())
                    logger.warn("exception occurred on login thread login: %s", e)
                    return self.exit()
        return self.exit()

class EventHandler(threading.Thread):
    """ thread responsible for websocket event callbacks """
    def __init__(self, subscriber):
        threading.Thread.__init__(self)
        self.subscriber = subscriber
        self._exit = False

    def exit(self):
        """ exit thread """
        logger.debug("exiting subscription event handler thread")
        self._exit = True

    def run(self):
        while not self._exit:
            try:
                event = self.subscriber._ws.recv()
            except Exception as e:
                logger.debug("websocket recv closed: %s", e)
                return
            if len(event) > 0:
                # parse event, determine subscription_ids and callback
                # note subsciption_ids is list of subscriptions... 
                try:
                    js = json.loads(event)
                    js["_ts"] = time.time()
                    if "subscriptionId" in js:
                        for s_id in js["subscriptionId"]:
                            cb = self.subscriber._subscription_ids.get(s_id, None)
                            if cb is not None:
                                cb.execute_callback(js)
                            else:
                                logger.debug("ignorning event, no callback for %s", s_id)
                    else:
                        logger.debug("invalid ws event, no subscription_id: %s", js)
                except ValueError as e:
                    logger.debug("failed to parse ws event: %s", event)

class CallbackHandler(object):
    """ handles callback for event for single url with pause support """
    def __init__(self, url, subscription_id, callback, paused):
        self.url = url
        self.subscription_id = subscription_id
        self.callback = callback
        self.paused = paused
        self.event_q = Queue()

    def flush(self):
        # flush any pending events
        while not self.event_q.empty():
            self.event_q.get()

    def pause(self):
        # pause callbacks
        logger.debug("pausing url: %s", self.url)
        self.paused = True

    def resume(self):
        # trigger all callbacks before setting pause to false
        logger.debug("resume %s with queue-size %s", self.url, self.event_q.qsize())
        while not self.event_q.empty():
            event = self.event_q.get()
            try:
                self.callback(event)
            except Exception as e:
                logger.debug("Traceback:\n%s", traceback.format_exc())
                logger.warn("failed to execute event callback: %s", e)
        self.paused = False

    def execute_callback(self, event):
        # execute callback or queue event if currently paused
        if self.paused:
            self.event_q.put(event)
        else:
            try:
                self.callback(event)
            except Exception as e:
                logger.debug("Traceback:\n%s", traceback.format_exc())
                logger.warn("failed to execute event callback: %s", e)

class Subscriber(threading.Thread):
    """ thread responsible for event subscriptions """
    def __init__(self, session, resubscribe=True):
        threading.Thread.__init__(self)
        self._session = session
        # subscriptions indexed by url with pointer to subscription_id
        self._subscriptions = {}
        # indexed by subscription_id with pointer to CallbackHandler
        self._subscription_ids = {}     
        # callbacks indexed by url with pointer to callback function
        self._callbacks = {}
        self._ws = None
        self._ws_url = None
        self._refresh_time = 30
        self._exit = False
        self._event_q = Queue()
        self.resubscribe = resubscribe
        self.event_handler_thread = None

    def exit(self):
        """ exit the thread and ensure event handler thread is also closed """
        logger.debug("exiting subscription thread")
        self._exit = True
        # close any open websockets
        self._close_web_socket()
        # cleanup pointers
        for (cb, _id) in self._subscription_ids.items():
            cb.flush()
        self._subscription_ids = {}
        self._subscriptions = {}
        self._callbacks = {}

    def run(self):
        """ run subscriber thread, listening for new subscription requests """
        while not self._exit:
            # refresh required every 60 seconds, static to 30 seconds for this module
            time.sleep(self._refresh_time)
            try:
                if not self.refresh_subscriptions():
                    logger.warn("failed to refresh one or more subscription")
                    return self.exit()
            except Exception as e:
                logger.debug("Traceback:\n%s", traceback.format_exc())
                logger.warn("failed to refresh subscriptions, exiting thread")
                return self.exit()

    def pause(self, url):
        """ pause and buffer callbacks for events for single url"""
        logger.debug("pausing url %s", url)
        if url in self._subscriptions:
            _id = self._subscriptions[url]
            if _id in self._subscription_ids:
                self._subscription_ids[_id].pause()
        else:
            logger.debug("ignoring pause for unknown url: %s", url)

    def resume(self, url):
        """ unpause and trigger callback execution for all pending events """
        # trigger all callbacks before setting pause to false
        if url in self._subscriptions:
            _id = self._subscriptions[url]
            if _id in self._subscription_ids:
                self._subscription_ids[_id].resume()
        else:
            logger.debug("ignoring resume for unknown url: %s", url)

    def refresh_subscriptions(self):
        """ refresh all subscriptions
            if any refresh fails then force resubscribe for all.
            return bool success
        """
        # cache result in case new subscription added during refresh
        logger.debug("refreshing %s subscriptions", len(self._subscriptions))
        subscriptions = [ _id for (k, _id) in self._subscriptions.items() ]
        refreshed_all = True
        for _id in subscriptions:
            refreshed = False
            try:
                refreshed = self._session.get("/api/subscriptionRefresh.json?id=%s" % _id).ok
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logger.warn("requests exception on refresh of %s: %s", _id, e)
            if not refreshed:
                logger.debug("failed to refresh subscription id %s", _id)
                refreshed_all = False
                break
        if not refreshed_all:
            return self._resubscribe()
        return refreshed_all

    def subscribe(self, url, callback, only_new=True, paused=False):
        """ subscribe to a particular apic url
            
            url (str)           relatively url in which to subscribe
            callback (func)     callback function triggered when event is received for url
            only_new (bool)     trigger callback only for new events received on subscription
            paused (bool)       start subscription in paused mode which buffers events instead of
                                triggering callback

            return bool success
        """
        # if only_new is false then force page-size to 1
        if only_new and "page-size" not in url:
            if "?" in url: url = "%s&page-size=1" % url
            else: url = "%s?page-size=1" % url

        #logger.debug('subscribing to url: %s', url)
        if self._ws is None or not self._ws.connected:
            if not self._open_web_socket():
                return False
        # skip duplicate calls
        if url in self._subscriptions:
            logger.debug("already subscribed to url")
            return True
        # validate callback is callable, else raise exception
        if not callable(callback):
            raise Exception("callback is not callable: %s", str(callback))
        self._callbacks[url] = callback
        return self._send_subscription(url, callback, only_new, paused)

    def unsubscribe(self, url):
        """ unsubscribe from a particular apic url """
        if url in self._subscriptions:
            self._callbacks.pop(url, None)
            _id = self._subscriptions.pop(url, None)
            self._subscription_ids.pop(_id, None)
            unsubscribe_url = re.sub("subscription=yes", "subscription=no", url)
            try:
                resp = self._session.get(unsubscribe_url)
                logger.debug("unsubscribe success: %r, url %s", resp.ok, unsubscribe_url)
            except Exception as e:
                #logger.debug("Traceback:\n%s", traceback.format_exc())
                logger.debug("failed to unsubscribe while exiting subscription: %s", e)

    def _close_web_socket(self):
        """ close websocket if connnected """
        # best effort attempt to unsubscribe from events 
        subscriptions = self._subscriptions.keys()
        for url in subscriptions:
            self.unsubscribe(url)

        if self._ws is not None:
            if self._ws.connected:
                logger.debug("closing connected web socket")
                self._ws.close()
                if self.event_handler_thread is not None:
                    self.event_handler_thread.exit()

    def _open_web_socket(self):
        """ open new web socket, return bool success"""
        # close any open websockets first
        self._close_web_socket()

        # if no token is present then need to trigger login
        if self._session.token is None:
            if not self._session.login():
                logger.warn("aborting web socket, unable to acquire login token")
                return False
        sslopt = {}
        if re.search("^https", self._session.api):
            sslopt['cert_reqs'] = ssl.CERT_NONE
            self._ws_url = 'wss://%s/socket%s' % (self._session.hostname, self._session.token)
        else:
            self._ws_url = 'ws://%s/socket%s' % (self._session.hostname, self._session.token)
        try:
            logger.debug("opening web socket")
            self._ws = create_connection(self._ws_url, sslopt=sslopt)
            if self._ws.connected:
                self.event_handler_thread = EventHandler(self)
                self.event_handler_thread.daemon = True
                self.event_handler_thread.start()
                return True
            else:
                logger.warn('unable to open websocket connection')
        except WebSocketException:
            logger.error('unable to open websocket connection due to WebSocketException')
        except socket.error:
            logger.error('unable to open websocket connection due to Socket Error')
        return False

    def _send_subscription(self, url, callback, only_new, paused):
        """ send the subscription to the specified url 
            return bool success
        """
        try:
            resp = self._session.get(url)
            if not resp.ok:
                self._subscriptions.pop(url, None)
                logger.warn('could not send subscription to APIC for url %s', url)
                return False
            resp_data = json.loads(resp.text)
            if 'subscriptionId' in resp_data:
                subscription_id = resp_data['subscriptionId']
                cb = CallbackHandler(url, subscription_id, callback, paused)
                self._subscriptions[url] = subscription_id
                self._subscription_ids[subscription_id] = cb
                logger.debug("subscription id %s for %s", subscription_id, url)
                # callback for non-new events
                if not only_new:
                    # trigger callback for each object
                    ts = time.time()
                    for obj in resp_data["imdata"]:
                        cb.execute_callback({
                            "imdata": [ obj ] ,
                            "subscriptionId": [ subscription_id ],
                            "_ts": ts
                        })
                return True
            else:
                logger.warn("invalid subscription response: %s", resp_data)
        except ConnectionError:
            self._subscriptions.pop(url, None)
            logger.warn("connection error occurred")
        except Exception as e:
            logger.debug("Traceback:\n%s", traceback.format_exc())

        logger.debug("failed to _send_subscription for url %s", url)
        return False

    def _resubscribe(self):
        """ restart websocket and resubscribe to urls. Triggered under the following scenarios:
            1) login thread refresh failure
            2) refresh subscriptions failure when resubscribe is enabled

            return bool success
        """
        if not self.resubscribe:
            logger.debug("cannot restart subscriptions as resubscribe is disabled")
            return False
        logger.debug("restarting all subscriptions")
        urls = self._subscriptions.keys()
        for (cb, _id) in self._subscription_ids.items():
            cb.flush()
        self._subscription_ids = {}
        self._subscriptions = {}
        for url in urls:
            if url not in self._callbacks:
                logger.warn("skipping subscribe, no callback found for url %s", url)
            else:
                if not self.subscribe(url, self._callbacks[url]):
                    return False
        return True


