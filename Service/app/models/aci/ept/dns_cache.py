
from . ept_cache import hitCache
from . ept_cache import hitCacheNotFound

import dns.resolver
import re
import logging
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class DNSEntry(object):
    def __init__(self, name, query_type, answer=None, ttl=None):
        self.name = name
        self.query_type = query_type
        self.answer = answer
        self.ttl = ttl

    def __repr__(self):
        delta = self.ttl - time.time()
        return "%s::%s [%s] [ttl: %0.3f, delta: %0.3f]" % (self.query_type, self.name, self.answer, 
                self.ttl, delta)

class DNSCache(object):
    """ In-memory DNS Cache object that tracks record type and record result """
    def __init__(self, resolver=None, max_records=10, timeout=10):
        # resolver can be list of IP addresses for DNS lookup or single string
        self.cache = hitCache(max_records)
        self.resolver = dns.resolver.Resolver()
        if resolver is not None:
            if isinstance(resolver, basestring):
                resolver = [resolver]
            self.resolver.nameservers = resolver
        self.resolver.timeout = timeout

    def dns_lookup(self, name, query_type="A"):
        """ perform dns lookup for A record or MX record for provided name. On success return string
            DNS result. For MX lookup return only result with lowest preference. Return None if
            unable to resolve DNS
        """
        ts = time.time()
        keystr = "%s::%s" % (query_type, name)
        dns_record = self.cache.search(keystr)
        if not isinstance(dns_record, hitCacheNotFound):
            logger.debug("(from cache) %s", dns_record)
            if ts is None or ts <= dns_record.ttl:
                return dns_record.answer
            else:
                logger.debug("ttl expired, removing from cache")
                self.cache.remove(keystr)

        # create a dummy dns_entry that we will cache on success of failure
        dns_entry = DNSEntry(name, query_type, ttl=ts+60)
        logger.debug("performing DNS lookup for %s", keystr)
        if query_type == "A":
            # if an IP address was provided then we can cache the address and the result directly
            if re.search("^[0-9\.]+$", name):
                logger.debug("skipping DNS lookup for IPv4 address %s", name)
                dns_entry.answer = name
                dns_entry.ttl = ts + 31536000   # 1 year cache 
            else:
                try:
                    record = self.resolver.query(name, "A")
                    if len(record) > 0:
                        dns_entry.answer = record[0].address
                        dns_entry.ttl = record.expiration
                except Exception as e:
                    logger.warn("failed to resolve A record for '%s': %s", name, e)
                    logger.debug(traceback.format_exc())
        elif query_type == "MX":
            try:
                preferred = None
                record = self.resolver.query(name, "MX")
                for subrecord in record:
                    if preferred is None or subrecord.preference < preferred.preference:
                        preferred = subrecord
                if preferred is None:
                    logger.warn("no valid MX record found")
                else:
                    dns_entry.answer = preferred.exchange.to_text()
                    dns_entry.ttl = record.expiration
            except Exception as e:
                logger.warn("failed to resolve MX record for domain '%s': %s", name, e)
                logger.debug(traceback.format_exc())
        else:
            logger.error("unsupported query type '%s'", query_type)
            return None

        # add result to cache and return dns_entry.address even if it is None
        logger.debug("DNS result for %s: %s", keystr, dns_entry.answer)
        self.cache.push(keystr, dns_entry)
        return dns_entry.answer

