import logging
from ..rest import (Rest, api_register)

@api_register(path="/aci/nodes", parent="fabric")
class Node(Rest):
    pass

