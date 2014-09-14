#!/usr/bin/env python

"""
:copyright: (c) 2014 by Mike Taylor
:license: MIT, see LICENSE for more details.

Walk thru a list of resources to extract possible IndieWeb domains from.
"""

import os, sys
import json
import collections
import requests

from urlparse import urlparse, ParseResult
from mf2py.parser import Parser

class Domain(object):
    """An Indieweb Domain"""

    def __init__(self, url, domainPath):
        self.domainPath = domainPath
        self.domain     = None
        self.url        = None
        self.domainFile = None

        item = urlparse(url)
        if item.scheme in ('http', 'https'):
            self.domain = item.netloc
            self.url    = url
        else:
            self.domain = item.path

        self.dataFile = os.path.abspath(os.path.expanduser(os.path.join(self.domainPath, self.domain)))

        if self.url is None:
            if os.path.exists(self.dataFile):
                with open(self.dataFile, 'r') as h:
                    data     = json.load(h)
                    self.url = data['url']
            else:
                self.url = 'http://%s' % self.domain

    def refresh(self):
        data = { 'url': self.url,
                 'domain': self.domain,
                 'mf2': {},
               }
        try:
            r = requests.get(self.url, verify=False)
            data['refresh'] = r.status_code
            if r.status_code == requests.codes.ok:
                if 'charset' in r.headers.get('content-type', ''):
                    html = r.text
                else:
                    html = r.content
                data['mf2'] = Parser(doc=html).to_dict()

        except:
            data['refresh'] = '%s' % sys.exc_info()[0]
        with open(self.dataFile, 'w') as h:
            h.write(json.dumps(data))

class Domains(collections.OrderedDict):
    """A collection of Indieweb Domains"""

    def __init__(self, dataPath, domainPath, domainFile):
        super(Domains, self).__init__()
        self.dataPath   = dataPath
        self.domainPath = domainPath
        self.domainFile = os.path.abspath(os.path.expanduser(os.path.join(self.dataPath, domainFile)))

        self.load()

    def load(self):
        if os.path.exists(self.domainFile):
            with open(self.domainFile, 'r') as h:
                for line in h.readlines():
                    domain = Domain(line.strip(), self.domainPath)
                    if domain.domain is not None:
                        self[domain.domain] = domain

    def store(self):
        with open(self.domainFile, 'w') as h:
            for key in self.keys():
                domain = self[key]
                h.write('%s\n' % domain.domain)
