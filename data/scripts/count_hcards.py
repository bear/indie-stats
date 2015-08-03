#!/usr/bin/env python

# count_hcards.sh domain workdir datajson resultjson

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
    counts[ts] = { 'h-card': 0 }
    with open(os.path.join(args.workdir, f)) as h:
        d = json.load(h)
        if 'mf2' in d and 'items' in d['mf2']:
            for item in d['mf2']['items']:
                if 'h-card' in item['type']:
                    counts[ts]['h-card'] += 1

with open(args.resultjson, 'w') as h:
    h.write(json.dumps(counts))
