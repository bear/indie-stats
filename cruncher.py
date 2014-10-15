#!/usr/bin/env python

"""
:copyright: (c) 2014 by Mike Taylor
:license: MIT, see LICENSE for more details.

Determine what new mf2 data needs to be parsed and
walk thru a list of stat generating scripts
"""

import os, sys
import json
import shutil
import logging
import tempfile
import subprocess

from domains import Domains, Domain

# import pprint
# pp = pprint.PrettyPrinter(indent=4)

log = logging.getLogger('gather')

def saveResults(domain, script, resultFile):
    statsFile = os.path.join(cfg['domainPath'], domain, 'stats_%s.json' % domain)
    stats     = {}
    results   = {}

    # stats are assumed to be in the following format:
    # { "20141004": { "count_hcards.py": { "h-card": 1 }}, 
    #   "20141001": { "count_hcards.py": { "h-card": 1 }}, 
    #   "20140930": { "count_hcards.py": { "h-card": 1 }}, 
    #   "20140926": { "count_hcards.py": { "h-card": 1 }}
    # }
    if os.path.exists(statsFile):
        with open(statsFile, 'r') as h:
            stats = json.load(h)

    # results are assumed to be in the following format:
    # { "20141004T164138": {"h-card": 1}, 
    #   "20141001T072243": {"h-card": 1}, 
    #   "20140930T073527": {"h-card": 1}, 
    #   "20140926T072253": {"h-card": 1}
    # }
    if os.path.exists(resultFile):
        with open(resultFile, 'r') as h:
            results = json.load(h)

        for key in results.keys():
            resultDate = key.split('T')[0]
            if resultDate not in stats:
                stats[resultDate] = {}
            stats[resultDate][script] = results[key] 

        with open(statsFile, 'w') as h:
            h.write(json.dumps(stats))

def process(cfg, scripts, pendingData):
    log.info('calling %d scripts for %d domains' % (len(scripts), len(pendingData)))

    for domain in pendingData.keys():
        for script in scripts:
            scriptFile = os.path.join(cfg['dataPath'], 'scripts', script)
            tempDir    = tempfile.mkdtemp(prefix='cruncher')
            resultFile = os.path.join(tempDir, '%s_results.json' % script)
            dataFile   = os.path.join(tempDir, '%s_files.json'   % script)

            for f in os.listdir(tempDir):
                os.remove(os.path.join(tempDir, f))
            with open(dataFile, 'w') as h:
                h.write(json.dumps(pendingData[domain]))
            if os.path.exists(resultFile):
                os.path.rmfile(resultFile)
            for f in pendingData[domain]:
                shutil.copyfile(os.path.join(cfg['domainPath'], domain, f), os.path.join(tempDir, f))
            log.info('%s %s %s %s %s' % (scriptFile, domain, tempDir, dataFile, resultFile))
            try:
                subprocess.call([scriptFile, domain, tempDir, dataFile, resultFile])
                saveResults(domain, script, resultFile)
            except:
                log.error('%s' % scriptFile)

def getSeenData(domain):
    seenFilename = os.path.join(domain.domainPath, 'processed.json')
    if os.path.exists(seenFilename):
        with open(seenFilename, 'r') as h:
            try:
                seenData = json.load(h)
            except:
                seenData = {}
    else:
        seenData = {}
    return seenData

def getPendingData(cfg, domains):
    log.info('searching domains for new files')
    pending = {}
    for key in domains:
        domain       = domains[key]
        domainFile   = '%s.json' % key
        seen         = getSeenData(domain)
        pending[key] = []

        for f in os.listdir(domain.domainPath):
            if f != domainFile and os.path.isfile(os.path.join(domain.domainPath, f)):
                if f not in seen:
                    pending[key].append(f)
    log.info('%d domains found with pending files' % len(pending))
    return pending

def getScripts(cfg):
    scripts    = []
    scriptPath = os.path.join(cfg['dataPath'], 'scripts')
    for f in os.listdir(scriptPath):
        if os.path.isfile(os.path.join(scriptPath, f)):
            scripts.append(f)
    return scripts

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

    pendingData = getPendingData(cfg, domains)
    scripts     = getScripts(cfg)

    process(cfg, scripts, pendingData)
