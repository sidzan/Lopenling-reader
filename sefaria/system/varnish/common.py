from varnishadm import VarnishManager
from urllib.parse import urlparse
from http.client import HTTPConnection
from sefaria.local_settings import VARNISH_ADM_ADDR, VARNISH_HOST, VARNISH_FRNT_PORT, VARNISH_SECRET, FRONT_END_URL

from sefaria.utils.util import graceful_exception

import logging
logger = logging.getLogger(__name__)


with open (VARNISH_SECRET, "r") as sfile:
    secret=sfile.read().replace('\n', '')
manager = VarnishManager((VARNISH_ADM_ADDR,), secret)


# PyPi version of python-varnish has broken purge function.  We use this instead.
# Derived from https://github.com/justquick/python-varnish/blob/master/varnish.py
@graceful_exception(logger=logger, return_value=None)
def purge_url(url):
    """
    Do an HTTP PURGE of the given asset.
    The URL is run through urlparse and must point to the varnish instance not the varnishadm
    """
    url = urlparse(url)
    connection = HTTPConnection(VARNISH_HOST, VARNISH_FRNT_PORT)
    path = url.path or '/'
    connection.request('PURGE', '%s?%s' % (path, url.query) if url.query else path, '',
                       {'Host': url.hostname})
    response = connection.getresponse()
    if response.status != 200:
        logger.error('Purge of {}{} on host {} failed with status: {}'.format(path,
                                                                                  "?" + url.query if url.query else '',
                                                                                  url.hostname,
                                                                                  response.status))
    return response


