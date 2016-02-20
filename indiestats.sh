#!/bin/bash
cd /home/indiestats
python gather_domains.py --config /etc/indie-stats.cfg --seed --refresh
chown -R www-data:www-data /home/indiestats/domains/*
chown -R www-data:www-data /home/indiestats/domains.json
python cruncher.py --config /etc/indie-stats.cfg
python summarize.py --config /etc/indie-stats.cfg
