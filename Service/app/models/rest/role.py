
from flask import jsonify

class Role(object):
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
            for r in (Role.FULL_ADMIN, Role.USER, Role.BLACKLIST):
                if role == r: return True
        except ValueError as e: pass
        return False

    @staticmethod
    def get_default(): return Role.USER

