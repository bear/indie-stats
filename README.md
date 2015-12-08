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

# Data

For each domain the following is stored:

- domain name: the network location for the domain
- url: the full url used to retrieve the domain
- headers: any headers returned from the GET request
- status: the HTTP status code from the GET request
- polled: the timestamp when the GET request was made
- excluded: if the domain has been added to the exclude list by the domain owner
- claimed: if the domain has been claimed by the domain owner
- html: the raw html retrieved from the GET request
- mf2: mf2 dictionary from last get
- history: list of domain archive json files

When the domain is polled the current domain information is moved to an archive file and then the domain is fetched.

# API

Indie-Stats has a very simple API now that can be accessed from ```https://indie-stats.com/api/v1/``` and provides the following resources. By default all values are returned as JSON.


- ```/domains``` -- return a JSON list of all domains being tracked
- ```/domains/<domain>``` -- return the most recent information for the given domain
