"""
If enabled, universe if single parent for all classes within API. With subtree support,
this allows a user to read all objects/config from the API in single call which may or
may not be desirable
"""

import logging

from . import Rest
from . import api_register

# module level logging
logger = logging.getLogger(__name__)


@api_register(path="/uni")
class Universe(Rest):
    logger = logger
    META_ACCESS = {
        "create": False,
        "read": True,
        "update": False,
        "delete": False,
    }
    META = {}
