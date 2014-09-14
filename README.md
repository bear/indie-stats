# indie-stats

Indieweb site crawler and MF2 data collection tool

An implementation of the idea from https://snarfed.org/indie-stats

# Goals
- From a list of domains, gather and store data
- Identify server and tools if possible
- run site thru MF2 parser and store raw JSON
- gather u- data and add to list of domains

## Longer Term
- Aggregate stats and generate reports
- Make data available for exporting in a number crunching friendly format

# Structure

    data\
      domains.dat -- master list of domains
      domains\
          example.com -- json meta data
          example.com__data -- stats, one line per update - json format

# Meta Data

Stored per domain:
- domain name: unique key
- url
- mf2: mf2 dictionary from last get
- html: raw html from last get
- refresh: status code
- refreshed: utc timestamp