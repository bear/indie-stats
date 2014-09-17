#!/usr/bin/env python

"""
:copyright: (c) 2014 by Mike Taylor
:license: MIT, see LICENSE for more details.

Walk thru a list of resources to extract possible IndieWeb domains from.
"""

import os, sys
import time
import json
import collections
import requests

from urlparse import urlparse, ParseResult
from mf2py.parser import Parser

class Domain(object):
    """An Indieweb Domain"""

    def __init__(self, url, domainPath, polled=None, status=None, history=None):
        self.domainPath = os.path.abspath(os.path.expanduser(domainPath))
        self.domain     = None
        self.url        = None
        self.domainFile = None
        self.polled     = polled
        self.status     = status
        if history is None:
            self.history = []
        else:
            self.history = history

        item = urlparse(url)
        if item.scheme in ('http', 'https'):
            self.domain = item.netloc
            self.url    = url
        else:
            self.domain = item.path

        self.dataFile = os.path.join(self.domainPath, self.domain)

        if self.url is None:
            if os.path.exists(self.dataFile):
                with open(self.dataFile, 'r') as h:
                    try:
                        data     = json.load(h)
                        self.url = data['url']
                    except:
                        self.url = 'http://%s' % self.domain
            else:
                self.url = 'http://%s' % self.domain

    def asDict(self):
        return { 'domain':  self.domain,
                 'url':     self.url,
                 'status':  self.status,
                 'polled':  self.polled,
                 'history': self.history
               }

    def refresh(self):
        ts     = time.gmtime()
        self.polled = time.strftime('%Y-%m-%dT%H:%M:%SZ', ts)
        data        = { 'url': self.url,
                        'domain': self.domain,
                         'mf2': {},
                         'html': '',
                         'status': 500,
                         'polled': self.polled
                      }
        try:
            r = requests.get(self.url, verify=False)
            if r.status_code == requests.codes.ok:
                if 'charset' in r.headers.get('content-type', ''):
                    html = r.text
                else:
                    html = r.content
                data['html'] = html
                data['mf2']  = Parser(doc=html).to_dict()
            data['status'] = r.status_code
        except:
            data['status'] = 500
        self.history.insert(0, data['status'])
        data['history'] = self.history
        with open(self.dataFile, 'w') as h:
            h.write(json.dumps(data, indent=2))
        statFile = os.path.join(self.domainPath, '%s_%s' % (time.strftime('%Y%m%dT%H%M%S', ts), self.domain))
        with open(statFile, 'w') as h:
            h.write(json.dumps(data, indent=2))
        return data

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
                    self[item['domain']] = Domain(item['url'], self.domainPath, item['polled'], item['status'], item['history'])

    def store(self):
        data = []
        for key in self.keys():
            data.append(self[key].asDict())        
        with open(self.domainFile, 'w') as h:
            h.write(json.dumps(data, indent=2))