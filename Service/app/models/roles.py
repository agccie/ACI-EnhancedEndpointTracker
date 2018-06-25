
from flask import jsonify

class Roles(object):
    """ Static Roles """
    FULL_ADMIN  = 0
    USER        = 1
    BLACKLIST   = 2
    ROLES_STR   = {
        FULL_ADMIN: "admin",
        USER: "user",
        BLACKLIST: "blacklist"
    }

    MIN_ROLE    = FULL_ADMIN
    MAX_ROLE    = BLACKLIST

    @staticmethod
    def valid(role):
        """ return true if role is valid else returns false """
        try:
            role = int(role)
            for r in (Roles.FULL_ADMIN, Roles.USER, Roles.BLACKLIST):
                if role == r: return True
        except ValueError as e: pass
        return False

    @staticmethod
    def get_default(): return Roles.USER

def api_read_roles():
    """ return mapping of role value to role name """
    return jsonify(Roles.ROLES_STR)

