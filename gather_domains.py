#!/usr/bin/env python

"""
:copyright: (c) 2014 by Mike Taylor
:license: MIT, see LICENSE for more details.

Walk thru a list of resources to extract possible IndieWeb domains from.
"""

import os, sys
import json
import logging

import requests
from domains import Domains, Domain
from mf2py.parser import Parser

# import pprint
# pp = pprint.PrettyPrinter(indent=4)

log = logging.getLogger('gather')


def gather(cfg, domains):
    r = requests.get(cfg['IRCPeople'], verify=False)
    log.info('IRCPeople request returned %s' % r.status_code)
    if r.status_code == requests.codes.ok:
        if 'charset' in r.headers.get('content-type', ''):
            html = r.text
        else:
            html = r.content
        mf2 = Parser(doc=html).to_dict()
        n   = 0
        if 'items' in mf2:
            for item in mf2['items']:
                if 'children' in item:
                    for child in item['children']:
                        if 'properties' in child:
                            url = child['properties']['url'][0]
                            if len(url) > 0:
                                domain = Domain(url, cfg['domainPath'])
                                if domain.domain not in domains:
                                    log.info('%s not found in domain list' % domain.domain)
                                    n += 1
                                    domains[domain.domain] = domain
        # {   'alternates': [   {   'rel': u'meta',
        #                           'type': u'application/rdf+xml',
        #                           'url': u'/wiki/index.php?title=IRC_People&action=dublincore'},
        #                       {   'type': u'application/atom+xml',
        #                           'url': u'/wiki/index.php?title=Special:RecentChanges&feed=atom'}],
        #     'items': [   {   'properties': {   u'logo': [   u'https://indiewebcamp.com/wiki/skins/indieweb/indiewebcamp-logo-500px.png'],
        #                                        'name': [u'IndieWebCamp'],
        #                                        'photo': [   u'https://indiewebcamp.com/wiki/skins/indieweb/indiewebcamp-logo-500px.png'],
        #                                        'url': [u'/']},
        #                      'type': [u'h-x-app']},
        #                  {   'children': [   {   'properties': {   u'name': [   u'_6a68'],
        #                                                            u'nickname': [   u'_6a68'],
        #                                                            u'tz': [   u'America/Los_Angeles'],
        #                                                            u'url': [   u'http://6a68.net']},
        #                                          'type': [u'h-card'],
        #                                          'value': u' _6a68 (America/Los_Angeles)'},
        #                                      {   'properties': {   u'name': [   u'aaronpk'],
        #                                                            u'nickname': [   u'aaronpk'],
        #                                                            u'photo': [   u'https://aaronparecki.com/images/aaronpk-128.jpg'],
        #                                                            u'tz': [   u'US/Pacific'],
        #                                                            u'url': [   u'http://aaronparecki.com']},
        #                                          'type': [u'h-card'],
        #                                          'value': u' aaronpk (US/Pacific)'},

        log.info('%d new domains added' % n)

def refresh(cfg, domains):
    log.info('refreshing domains')
    for key in domains:
        domain = domains[key]
        result = domain.refresh()
        log.info('%s: %s' % (domain.domain, result['status']))

def initLogging(logger, logpath=None, echo=False):
    logFormatter = logging.Formatter("%(asctime)s %(levelname)-9s %(message)s", "%Y-%m-%d %H:%M:%S")

    if logpath is not None:
        logfilename = os.path.join(logpath, 'gather_domains.log')
        logHandler  = logging.FileHandler(logfilename)
        logHandler.setFormatter(logFormatter)
        logger.addHandler(logHandler)

    if echo:
        echoHandler = logging.StreamHandler()
        echoHandler.setFormatter(logFormatter)
        logger.addHandler(echoHandler)

    logger.setLevel(logging.INFO)


def loadConfig(configFilename):
    filename = os.path.abspath(os.path.expanduser(configFilename))
    cfg      = {}
    if os.path.exists(filename):
        with open(filename, 'r') as h:
            cfg = json.load(h)
    else:
        print('creating default configuration at %s' % filename)
        cwd = os.getcwd()
        cfg['dataPath']  = os.path.join(cwd, 'data')
        cfg['datastore'] = 'files'
        cfg['domains']   = 'domains.dat'
        cfg['domainPath']   = os.path.join(cfg['dataPath'], 'mf2data')
        cfg['IRCPeople'] = 'http://indiewebcamp.com/IRC-people'
        with open(filename, 'w') as h:
            json.dump(cfg, h, indent=2)

        if not os.path.exists(cfg['dataPath']):
            print('creating dataPath %s' % cfg['dataPath'])
            os.mkdir(cfg['dataPath'])
        if not os.path.exists(cfg['domainPath']):
            print('creating domainPath %s' % cfg['domainPath'])
            os.mkdir(cfg['domainPath'])

    return cfg


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--config',  default='./indie-stats.cfg')
    parser.add_argument('--echo',    default=True,  action='store_true')
    parser.add_argument('--gather',  default=False, action='store_true')
    parser.add_argument('--refresh', default=False, action='store_true')

    args = parser.parse_args()
    cfg  = loadConfig(args.config)

    initLogging(log, cfg['dataPath'], args.echo)

    log.info('starting')

    domains = Domains(cfg['dataPath'], cfg['domainPath'], cfg['domains'])
    log.info('%d domains loaded from datastore' % len(domains))

    if args.gather:
        gather(cfg, domains)

    if args.refresh:
        refresh(cfg, domains)

    domains.store()
