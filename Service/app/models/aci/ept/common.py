"""
common ept functions
"""
import logging
import re
import time

# module level logging
logger = logging.getLogger(__name__)

###############################################################################
#
# shared globals
#
###############################################################################

HELLO_INTERVAL = 1.0
HELLO_TIMEOUT = 5.0
SEQUENCE_TIMEOUT = 100
MANAGER_CTRL_CHANNEL = "mctrl"
MANAGER_WORK_QUEUE = "mq"
WORKER_CTRL_CHANNEL = "wctrl"
WORKER_UPDATE_INTERVAL = 1.0

# minimum version of supported code (2.2.1n)
MINIMUM_SUPPORTED_VERSION = "2.2.1n"

# dynamic imports of MOs need base relatively to full project
MO_BASE = "app.models.aci.mo"

###############################################################################
#
# initializing functions
#
###############################################################################

def wait_for_redis(redis_db, check_interval=1):
    """ blocking function that waits until provided redis-db is available """
    while True:
        try:
            if redis_db.dbsize() >= 0:
                logger.debug("successfully connected to redis db")
                return
        except Exception as e:
            logger.debug("failed to connect to redis db: %s", e)
        if check_interval > 0:
            time.sleep(check_interval)

def wait_for_db(db, check_interval=1):
    """ blocking function that waits until provided mongo-db is available """
    while True:
        try:
            if len(db.collection_names()) >= 0:
                logger.debug("successfully connected to mongo db")
                return 
        except Exception as e:
            logger.debug("failed to connect to mongo db: %s", e)
        if check_interval > 0:
            time.sleep(check_interval)

###############################################################################
#
# ept specific functions
#
###############################################################################

def get_vpc_domain_id(n1, n2):
    """ calculate interger vpc_domain_id for two node ids
        id is always (highest node id) << 16 + (lower node id)
    """
    n1 = int(n1)
    n2 = int(n2)
    if n1 > n2: return (n1 << 16) + n2
    return (n2 << 16) + n1
    

###############################################################################
#
# common conversion functions
#
###############################################################################

def get_mac_string(mac):
    """ takes 48-bit (12 character) integer and returns dotted mac """
    return "{0:04x}.{1:04x}.{2:04x}".format(
        (mac & 0xffff00000000) >> 32,
        (mac & 0xffff0000) >> 16 ,
        mac & 0xffff
    )

mac_reg = "^(?P<o1>[a-f0-9]{1,4})[.\-:]"
mac_reg+= "(?P<o2>[a-f0-9]{1,4})[.\-:]"
mac_reg+= "(?P<o3>[a-f0-9]{1,4})$"
mac_reg = re.compile(mac_reg, re.IGNORECASE)
def get_mac_value(mac):
    """ takes mac string and returns 48-bit integer. this will support the following formats:
            E                   (single integer in hex format)
            E.E.E
            EE-EE-EE-EE-EE-EE
            EE.EE.EE.EE.EE.EE
            EEEE.EEEE.EEEE
        returns 0 on error
    """
    mac = "%s" % mac
    # either matches mac_reg or able to cast with base 16
    r1 = mac_reg.search(mac)
    if r1 is not None:
        o1 = int(r1.group("o1"),16) << 32
        o2 = int(r1.group("o2"),16) << 16
        o3 = int(r1.group("o3"),16)
        return o1+o2+o3
    try: return int(re.sub("[.\-:]","",mac),16)
    except Exception as e: 
        logger.warn("failed to convert mac '%s' to integer: %s", mac, e)
        return 0

def get_ip_prefix(ip):
    """ receives ipv4 or ipv6 string with or without mask, determines if the address is ipv4 or ipv6,
        then returns result of get_ipv4_prefix or get_ipv6_prefix
    """
    if ":" in ip:
        return get_ipv6_prefix(ip)
    return get_ipv4_prefix(ip)

def get_ipv4_string(ipv4):
    """ takes 32-bit integer and returns dotted ipv4 """
    return "%s.%s.%s.%s" % (
        (ipv4 & 0xff000000) >> 24,
        (ipv4 & 0xff0000) >> 16,
        (ipv4 & 0xff00) >> 8 ,
        ipv4 & 0xff
    )

ipv4_prefix_reg = "^(?P<o0>[0-9]+)\.(?P<o1>[0-9]+)\.(?P<o2>[0-9]+)\."
ipv4_prefix_reg+= "(?P<o3>[0-9]+)(/(?P<m>[0-9]+))?$"
ipv4_prefix_reg = re.compile(ipv4_prefix_reg)
def get_ipv4_prefix(ipv4):
    """ takes ipv4 string with or without prefix present and returns tuple:
            (address, mask) where addr and mask are 32-bit ints
        if no mask is present, the /32 is assumed
        mask is '1-care' format.  For example:
            /0  = 0x00000000
            /8  = 0xff000000
            /16 = 0xffff0000
            /24 = 0xffffff00
            /32 = 0xffffffff
        returns (None,None) on error
    """
    r1 = ipv4_prefix_reg.search(ipv4)
    if r1 is None:
        logger.warn("address %s is invalid ipv4 address", ipv4)
        return (None, None)
    if r1.group("m") is not None: mask = int(r1.group("m"))
    else: mask = 32
    oct0 = int(r1.group("o0"))
    oct1 = int(r1.group("o1"))
    oct2 = int(r1.group("o2"))
    oct3 = int(r1.group("o3"))
    if oct0 > 255 or oct1 > 255 or oct2 > 255 or oct3 > 255 or mask > 32:
        logger.warn("address %s is invalid ipv4 address", ipv4)
        return (None, None)

    addr = (oct0 << 24) + (oct1 << 16) + (oct2 << 8) + oct3
    mask = (~(pow(2,32-mask)-1)) & 0xffffffff
    return (addr&mask, mask)

def get_ipv6_string(ipv6):
    """ takes 64-bit integer and converts to ipv6 """
    s = "%x:%x:%x:%x:%x:%x:%x:%x" % (
        (ipv6 & 0xffff0000000000000000000000000000 ) >> 112,
        (ipv6 & 0x0000ffff000000000000000000000000 ) >> 96,
        (ipv6 & 0x00000000ffff00000000000000000000 ) >> 80,
        (ipv6 & 0x000000000000ffff0000000000000000 ) >> 64,
        (ipv6 & 0x0000000000000000ffff000000000000 ) >> 48,
        (ipv6 & 0x00000000000000000000ffff00000000 ) >> 32,
        (ipv6 & 0x000000000000000000000000ffff0000 ) >> 16,
        (ipv6 & 0x0000000000000000000000000000ffff )
    )
    # ipv6 best practice to replaces multiple 0-octects with ::
    return re.sub(":[0:]+", "::", s, 1)

ipv6_prefix_reg = re.compile("^(?P<addr>[0-9a-f:]{2,40})(/(?P<m>[0-9]+))?$", re.IGNORECASE)
def get_ipv6_prefix(ipv6):
    """ takes ipv6 string with or without prefix present and returns tuple:
            (address, mask) where addr and mask are 128-bit ints
        if no mask is present, the /128 is assumed
        mask is '1-care' format.  For example:
            /0  = 0x00000000 00000000 00000000 00000000
            /24 = 0xffffff00 00000000 00000000 00000000
            /64 = 0xffffffff ffffffff 00000000 00000000
            /128= 0xffffffff ffffffff ffffffff ffffffff
        returns (None,None) on error
    """
    r1 = ipv6_prefix_reg.search(ipv6)
    if r1 is None:
        logger.warn("address %s is invalid ipv6 address", ipv6)
        return (None, None)
    if r1.group("m") is not None: mask = int(r1.group("m"))
    else: mask = 128

    upper = []
    lower = []
    # split on double colon to determine number of double-octects to pad
    dc_split = r1.group("addr").split("::")
    if len(dc_split) == 0 or len(dc_split)>2:
        logger.warn("address %s is invalid ipv6 address", ipv6)
        return (None, None)
    if len(dc_split[0])>0:
        for o in dc_split[0].split(":"): upper.append(int(o,16))
    if len(dc_split)==2 and len(dc_split[1])>0:
        for o in dc_split[1].split(":"): lower.append(int(o,16))
    # ensure there are <=8 total double-octects including pad
    pad = 8 - len(upper) - len(lower)
    if pad < 0 or pad >8:
        logger.warn("address %s is invalid ipv6 address", ipv6)
        return (None, None)

    # sum double-octects with shift
    addr = 0
    for n in (upper + [0]*pad + lower): addr = (addr << 16) + n
    mask = (~(pow(2,128-mask)-1)) & 0xffffffffffffffffffffffffffffffff
    return (addr&mask, mask)


