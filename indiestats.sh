#!/bin/bash
cd /home/indiestats
python gather_domains.py --config /home/indiestats/indie-stats.cfg --seed --refresh
python cruncher.py --config /home/indiestats/indie-stats.cfg
python summarize.py --config /home/indiestats/indie-stats.cfg
