
from flask import abort, request, current_app
from pymongo import DESCENDING as py_descend
from pymongo import ASCENDING as py_ascend
import random, string, time, logging, re
# module level logger
logger = logging.getLogger(__name__)

# common message
MSG_403 = "Sorry old chap, this is a restricted area..."

def aes_encrypt(data, **kwargs):
    # return AES encrypted data hexstring (None on failure)
    from Crypto.Cipher import AES
    import struct, binascii
    ekey = kwargs.get("ekey", None)
    eiv = kwargs.get("eiv", None)
    try:
        if ekey is None:
            ekey = current_app.config["EKEY"]
        if eiv is None:
            eiv = current_app.config["EIV"]
        ekey = ("%s" % ekey).decode("hex")
        eiv = ("%s" % eiv).decode("hex")
        ec = AES.new(ekey, AES.MODE_CBC, eiv)

        # pad data to 16 bytes (each pad byte is length of padding)
        # example - pad_count is 4.  Then pad "\x04\x04\x04\x04"
        data = data.encode("utf-8")
        pad_count = 16-len(data)%16
        data += struct.pack("B", pad_count)*pad_count
        # need to store data as hex string, so always return hex string
        edata = binascii.hexlify(ec.encrypt(data))
        return edata
    except Exception as e:
        logger.error("aes_encrypt %s" % e)

    return None
        
def aes_decrypt(edata, **kwargs):
    # return AES decrypted data from data hexstring (None on failure)
    from Crypto.Cipher import AES
    import struct, binascii
    ekey = kwargs.get("ekey", None)
    eiv = kwargs.get("eiv", None)
    try:
        if ekey is None:
            ekey = current_app.config["EKEY"]
        if eiv is None:
            eiv = current_app.config["EIV"]
        ekey = ("%s" % ekey).decode("hex")
        eiv = ("%s" % eiv).decode("hex")
        ec = AES.new(ekey, AES.MODE_CBC, eiv)

        # decrypt data hex string
        data = ec.decrypt(edata.decode("hex"))
        # need to remove padding from decrypted data - last byte should be
        # value between 0 and 15 representing number of characters to remove
        last_byte = ord(data[-1])
        if last_byte>0 and last_byte<=16 and len(data)>=last_byte:
            data = data[0:(len(data)-last_byte)]
        return data
    except Exception as e:
        logger.error("aes_decrypt error %s" % e)
    return None

def get_user_data(params=[], relaxed=False):
    # validate all fields are present in params list
    # set relaxed to True to prevent abort if data not found
    data = request.json
    if not data: 
        if not relaxed: abort(400)
        else: return {}
    # required paramaters
    for r in convert_to_list(params):
        if r not in data:
            abort(400, "Required parameter \"%s\" not provided" % r)    
    return data

def random_str(length=32):
    # http://en.wikipedia.org/wiki/Random_password_generator#Python
    alphabet = string.letters[0:52] + string.digits
    rstr = random.SystemRandom()
    return str().join(rstr.choice(alphabet) for _ in range(length))

def convert_to_list(obj):
    """ receives an object and if type tuple or list, return list. Else
        return a list containing the one object 
    """
    if type(obj) is None: return [] # None implies empty list...
    if type(obj) is list: return obj
    if type(obj) is tuple:
        return [x for x in obj]
    return [obj]

def combine_list(list1, list2):
    """ combine two lists without creating duplicate entries) """
    return list1 + list(set(list2) - set(list1))

def force_attribute_type(attr, attr_type, val, control=None):
    """ receives an attribute name and type and attempts to cast value
        to provided attribute.  If ValueError is raised, then aborts 
        request.  For list or dict, a subtype can be provided to
        force subtype to correct value.  Assumes all values are same subtype
        control - dict that can contain:
            subtype - for subtype verification
            min_val - minimum value for numbers
            max_val - maximum value for numbers
            regex - string regular expression
    """
    subtype = None
    min_val = None
    max_val = None
    regex = None
    values = None
    if control is not None:
        subtype = control.get("subtype", None)
        min_val = control.get("min_val", None)
        max_val = control.get("max_val", None)
        regex  = control.get("regex", None)
        values = control.get("values", None)
    try:
        # don't manually cast a 'list' (unexpected behavior for strings...)
        if attr_type is list and not isinstance(val, list):
            raise ValueError()
        # handle subtype for list or dict
        if subtype is not None:
            casted = attr_type(val)
            if attr_type is list:
                ret = []
                for v in casted: ret.append(subtype(v))
                return ret 
            elif attr_type is dict:
                ret = {}
                for k in casted: ret[k] = subtype(casted[k])
                return ret
        err = "Invalid value '%s' for attribute '%s'" % (val,attr)
        nval = attr_type(val)

        # check regex values
        if regex is not None:
            if not re.search(regex, nval): abort(400, err)
            return nval

        # check list of values
        if values is not None:
            if nval not in values: abort(400, err)
            return nval

        # check min/max values
        if min_val is not None and max_val is not None:
            err = "%s, must be between %s and %s" % (err, min_val, max_val)
        elif min_val is not None:
            err = "%s, must be greater than or equal to %s" %(err, min_val)
        elif max_val is not None:
            err = "%s, must be less than or equal to %s" % (err, max_val)
        if min_val is not None and nval<min_val:
            abort(400, err)
        if max_val is not None and nval>max_val:
            abort(400, err)
        return nval
    except ValueError as e: 
        err = "Invalid value '%s' for attribute '%s'. " % (val, attr)
        abort(400, err)

def current_tz_string():
    """ returns padded string UTC offset for current server
        +/-xxx
    """
    offset = time.timezone if (time.localtime().tm_isdst==0) else time.altzone
    offset = -1*offset
    ohour = abs(int(offset/3600))
    omin = int(((abs(offset))-ohour*3600)%60)
    if offset>0:
        return "+%s:%s" % ('{0:>02d}'.format(ohour),
                           '{0:>02d}'.format(omin))
        #return "+%s" % '{0:<03d}'.format(abs(offset))
    else:
        return "-%s:%s" % ('{0:>02d}'.format(ohour),
                           '{0:>02d}'.format(omin))
        #return "-%s" % '{0:<03d}'.format(abs(offset))

def filtered_read(collection, **kwargs):
    """ perform database query against provided collection and any
        provided filters along with user base filters.  If meta is provided
        then will use 'read' attribute to further filter which results 
        are returned.

        user can provide filters as parameters to API call.  Format TBD
        pymongo filter with regex: {"username":{"$regex":"^a"}}

        considerations:
            1) cannot overwrite or append to filter attribute
                if 'filter' contains "username", then cannot overwrite with 
                user provided filter
            2) if meta dict is provided in kwargs, then all query attributes
                will be validated and error produced for unexpected attribute
    """
    filters = kwargs.get("filters", {})
    projection = kwargs.get("projection", None) # field names to be returned
    sort = kwargs.get("sort", None) # single sort attribute for sorting result
    sort_descend = kwargs.get("sort_descend", False)
    limit = kwargs.get("limit", None)
    meta = kwargs.get("meta", None)
    su = kwargs.get("su", False)

    # add/adjust filters based on user provided params
    # TODO

    # verify filters are acceptable values based on provided meta data
    if meta is not None:
        for f in filters:
            if f not in meta:
                abort(400, "invalid filter attribute '%s'" % f)

    # prepare read attributes
    results = []
    read_attr = {}
    if meta is not None:
        for v in meta:
            if "read" in meta[v] and meta[v]["read"]: read_attr[v] = 1
  
    # build cursor based on sort and limit options
    cursor = collection.find(filters, projection=projection)
    if sort is not None: 
        if sort_descend: cursor = cursor.sort(sort, py_descend)
        else:  cursor = cursor.sort(sort, py_ascend) 
    if limit is not None: cursor = cursor.limit(limit)
 
    # perform no attribute filtering on results
    if meta is None:
        for r in cursor:
            results.append(r)
    # perform no attribute filtering for su but ensure all attributes are set
    elif su:
        for r in cursor:
            for v in meta:
                if v not in r: r[v] = meta[v]["default"]
            results.append(r)
    # perform attribute filtering on results but allow all meta attributes
    elif len(read_attr) == 0:
        for r in cursor:
            obj = {}
            for v in meta:
                if v in r: obj[v] = r[v]
            results.append(obj)
    # perform attribute filtering based only on read_attr
    else:
        for r in cursor:
            obj = {}
            for v in read_attr:
                if v in r: obj[v] = r[v]
                # if attribute is not present (for whatever reason), 
                # set attribute to it's default value
                else: obj[v] = meta[v]["default"]
            results.append(obj)

    return results
