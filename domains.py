#!/usr/bin/env python

"""
:copyright: (c) 2014 by Mike Taylor
:license: MIT, see LICENSE for more details.

Walk thru a list of resources to extract possible IndieWeb domains from.
"""

import os, sys
import time
import json
import requests

from urlparse import urlparse, ParseResult
from mf2py.parser import Parser

try:
    from collections import OrderedDict
except ImportError:
    # python 2.6 or earlier, use backport
    from ordereddict import OrderedDict


class Domain(object):
    """An Indieweb Domain"""

    def __init__(self, domain, domainPath):
        self.domainRoot = os.path.abspath(os.path.expanduser(domainPath))
        self.domain     = None
        self.url        = None
        self.domainPath = None
        self.domainFile = None
        self.ts         = None
        self.polled     = None
        self.status     = None
        self.excluded   = False
        self.claimed    = False
        self.found      = False
        self.html       = ''
        self.headers    = []
        self.history    = []

        self.load(domain)

    def load(self, domain):
        self.url        = 'http://%s' % domain
        self.domain     = domain.lower()
        self.domainPath = os.path.join(self.domainRoot, self.domain)
        self.domainFile = os.path.join(self.domainPath, '%s.json' % self.domain)

        if os.path.exists(self.domainFile):
            with open(self.domainFile, 'r') as h:
                try:
                    self.fromDict(json.load(h))

                    if self.polled is not None:
                        self.ts = time.strptime(self.polled, '%Y-%m-%dT%H:%M:%SZ')
                    self.found = True
                except:
                    self.found = False

        processedFile = os.path.join(self.domainPath, 'processed.json')
        if os.path.exists(processedFile):
            with open(processedFile, 'r') as h:
                try:
                    self.history = json.load(h)
                except:
                    self.history = []

    def asDict(self):
        return { 'domain':   self.domain,
                 'url':      self.url,
                 'html':     self.html,
                 'headers':  dict(self.headers),
                 'status':   self.status,
                 'polled':   self.polled,
                 'history':  self.history,
                 'excluded': self.excluded,
                 'claimed':  self.claimed,
               }

    def fromDict(self, data):
        for key in ('domain', 'url', 'html', 'headers', 'status', 'polled', 'history', 'excluded', 'claimed'):
            if key in data:
                setattr(self, key, data[key])

    def refresh(self):
        if not self.excluded:
            self.ts     = time.gmtime()
            self.polled = time.strftime('%Y-%m-%dT%H:%M:%SZ', self.ts)
            try:
                r = requests.get(self.url, verify=False)
                if r.status_code == requests.codes.ok:
                    if 'charset' in r.headers.get('content-type', ''):
                        self.html = r.text
                    else:
                        r.encoding = 'utf8'
                        self.html = r.text
                self.headers = r.headers
                self.status  = r.status_code
            except:
                self.status = 500

        return self.store()

    def store(self):
        data = self.asDict()
        if not self.excluded:
            try:
                data['mf2'] = Parser(doc=self.html, url=self.url).to_dict()
            except:
                data['mf2'] = {}
        if not os.path.exists(self.domainPath):
            os.mkdir(self.domainPath)

        if 'html' in data:
            try:
                data['html'] = data['html'].encode('utf8')
            except:
                data['html'] = ""

        sData = json.dumps(data, indent=2, ensure_ascii=False, encoding='utf8')

        with open(self.domainFile, 'w') as h:
            h.write(sData.encode('utf8'))
        if self.ts is not None:
            statFile = os.path.join(self.domainPath, '%s_%s.json' % (time.strftime('%Y%m%dT%H%M%S', self.ts), self.domain))
            with open(statFile, 'w') as h:
                h.write(sData.encode('utf8'))
        return data

class Domains(OrderedDict):
    """A collection of Indieweb Domains"""

    def __init__(self, dataPath, domainPath, domainFile):
        super(Domains, self).__init__()
        self.dataPath   = dataPath
        self.domainPath = domainPath
        self.domainFile = os.path.abspath(os.path.expanduser(os.path.join(self.dataPath, domainFile)))

        if not os.path.exists(self.domainPath):
            os.mkdir(self.domainPath)

        self.load()

    def load(self):
        if os.path.exists(self.domainFile):
            with open(self.domainFile, 'r') as h:
                try:
                    data = json.load(h)
                except:
                    data = []
            # assumes a structure of
            # [ { "domain":  "bear.im",
            #     "url":     "https://bear.im",
            #     "polled":  "2014-09-14T05:31:48Z",
            #     "status":  200,
            #     "history": [ 200, 200, 200, 200 ]
            #    }
            # ]
            for item in data:
                if 'domain' in item:
                    domain = Domain(item['url'], self.domainPath)
                    if domain.found:
                        self[item['domain']] = domain

        for f in os.listdir(self.domainPath):
            if f not in self:
                domain = Domain(f, self.domainPath)
                if domain.found:
                    self[domain.domain] = domain

    def store(self):
        data = []
        for key in self.keys():
            data.append(self[key].asDict())        
        with open(self.domainFile, 'w') as h:
            h.write(json.dumps(data, indent=2, ensure_ascii=False, encoding='utf8'))
