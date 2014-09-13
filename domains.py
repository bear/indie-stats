#!/usr/bin/env python

"""
:copyright: (c) 2014 by Mike Taylor
:license: MIT, see LICENSE for more details.

Walk thru a list of resources to extract possible IndieWeb domains from.
"""

import os, sys
import collections

import requests

class Domain(object):
    """An Indieweb Domain"""

    def __init__(self, url):
        self.url  = url
        self.data = {}

    def loadJson(self, filename):
        f = os.path.abspath(os.path.expanduser(filename))
        if os.path.exists(f):
            with open(f, 'r') as h:
                self.data = json.load(h)
        else:
            self.data = {}

class Domains(collections.OrderedDict):
    """A collection of Indieweb Domains"""

    def __init__(self, domainPath, domainFile=None):
        super(Domains, self).__init__()
        self.domainPath = domainPath
        self.domainFile = domainFile

        if self.domainFile is not None:
            self.load(self.domainFile)

    def load(self, domainFile):
        self.domainFile = domainFile
        f = os.path.abspath(os.path.expanduser(os.path.join(self.domainPath, self.domainFile)))
        if os.path.exists(f):
            with open(f, 'r') as h:
                for line in h.readlines():
                    url       = line.strip()
                    domain    = Domain(url)
                    self[url] = domain
                    domain.loadJson(os.path.join(self.domainPath, url))

    def store(self):
        f = os.path.abspath(os.path.expanduser(os.path.join(self.domainPath, self.domainFile)))
        with open(f, 'w') as h:
            for url in self.keys():
                h.write('%s\n' % url)
