#!/usr/bin/env python

"""
:copyright: (c) 2014 by Mike Taylor
:license: MIT, see LICENSE for more details.

look at all the stats files for each domain and
summarize global numbers
"""

import os, sys
import json
import logging

from domains import Domains, Domain

# import pprint
# pp = pprint.PrettyPrinter(indent=4)

log = logging.getLogger('summarize')


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

    args = parser.parse_args()
    cfg  = loadConfig(args.config)

    initLogging(log, cfg['dataPath'], args.echo)

    log.info('starting')

    domains = Domains(cfg['dataPath'], cfg['domainPath'], cfg['domains'])
    log.info('%d domains loaded from datastore' % len(domains))

    gStats = { 'domain_count':  0,
               'start_date':    'z',
               'end_date':      '',
               'error_polling': 0,
               'good_polling':  0,
               'mf_found':      0,
               'excluded':      0,
               'domains':       {},
             }
    for key in domains:
        domain    = domains[key]
        statsFile = os.path.join(cfg['domainPath'], key, 'stats_%s.json' % key)
        if os.path.exists(statsFile):
            with open(statsFile, 'r') as h:
                stats = json.load(h)

            gStats['domain_count'] += 1
            keys = stats.keys()
            keys.sort()
            if keys[0] < gStats['start_date']:
                gStats['start_date'] = keys[0]
            enddate = keys[-1]
            if keys[-1] == 'stats':
                enddate = keys[-2]
            if enddate > gStats['end_date']:
                gStats['end_date'] = enddate

            gStats['domains'][key] = stats

    f = os.path.join(cfg['dataPath'], 'summary.json')
    with open(f, 'w') as h:
        h.write(json.dumps(gStats))
