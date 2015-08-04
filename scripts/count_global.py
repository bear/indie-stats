#!/usr/bin/env python

import os, sys
import json
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('domain',)
parser.add_argument('workdir')
parser.add_argument('datajson')
parser.add_argument('resultjson')

args = parser.parse_args()

with open(args.datajson) as h:
    dataFiles = json.load(h)

counts = {}

for f in dataFiles:
    ts, t = f.split('_')
    counts[ts] = { 'error_polling': 0,
                   'good_polling':  0,
                   'mf_found':      0,
                   'excluded':      0,
                 }
    with open(os.path.join(args.workdir, f)) as h:
        d = json.load(h)
        if 'mf2' in d and len(d['mf2']) > 0:
            counts[ts]['mf_found'] += 1
        if 'excluded' in d and d['excluded']:
            counts[ts]['excluded'] += 1
        if 'status' in d:
            if d['status'] == 200:
                counts[ts]['good_polling'] += 1
            else:
                counts[ts]['error_polling'] += 1

with open(args.resultjson, 'w') as h:
    h.write(json.dumps(counts))
