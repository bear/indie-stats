#!/usr/bin/env python

"""
:copyright: (c) 2014 by Mike Taylor
:license: MIT, see LICENSE for more details.

A Flask web service to handle the dynamic bits of
the indie-stats.com site.
"""

import os, sys
import json
import time
import uuid
import urllib
import logging
import datetime

import redis
import requests

from urlparse import urlparse, ParseResult
from flask import Flask, request, redirect, render_template, session, flash, jsonify

from flask.ext.wtf import Form
from wtforms import TextField, HiddenField, BooleanField
from wtforms.validators import Required

import ninka
from domains import Domain, Domains

class LoginForm(Form):
    domain       = TextField('domain', validators = [ Required() ])
    client_id    = HiddenField('client_id')
    redirect_uri = HiddenField('redirect_uri')
    from_uri     = HiddenField('from_uri')

class DomainForm(Form):
    excluded  = BooleanField('excluded')
    client_id = HiddenField('client_id')

class DomainNotFoundForm(Form):
    client_id = HiddenField('client_id')

class IndexForm(Form):
    client_id = HiddenField('client_id')

# check for uwsgi, use PWD if present or getcwd() if not
_uwsgi = __name__.startswith('uwsgi')
if _uwsgi:
    _ourPath    = os.getenv('PWD', None)
    _configFile = '/etc/indie-stats.cfg'
else:
    _ourPath    = os.getcwd()
    _configFile = os.path.join(_ourPath, 'indie-stats.cfg')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'foo'  # replaced downstream
cfg = None
db  = None
templateData = {}

def clearAuth():
    if 'indieauth_token' in session:
        indieauth_token = session['indieauth_token']
        if db is not None:
            db.delete('token-%s' % indieauth_token)
    session.pop('indieauth_token', None)
    session.pop('indieauth_scope', None)
    session.pop('indieauth_id', None)

def checkAuth():
    authed        = False
    indieauth_id  = None
    authed_domain = None
    authed_url    = None
    if 'indieauth_id' in session and 'indieauth_token' in session:
        indieauth_id    = session['indieauth_id']
        indieauth_token = session['indieauth_token']
        app.logger.info('session cookie found')
        if db is not None:
            me = db.get('token-%s' % indieauth_token)
            if me:
                data = db.hgetall(me)
                if data and data['token'] == indieauth_token:
                    authed = True
    if authed:
        domain        = Domain(indieauth_id, cfg['domainPath'])
        authed_domain = domain.domain
        authed_url    = domain.url
    return authed, indieauth_id, authed_domain, authed_url

@app.route('/logout', methods=['GET'])
def handleLogout():
    app.logger.info('handleLogout [%s]' % request.method)
    clearAuth()
    return redirect('/')

@app.route('/login', methods=['GET', 'POST'])
def handleLogin():
    app.logger.info('handleLogin [%s]' % request.method)
    app.logger.info('client_id [%s] redirect_uri [%s/success]' % (cfg['client_id'], cfg['baseurl']))

    form = LoginForm(client_id=cfg['client_id'], 
                     redirect_uri='%s/success' % cfg['baseurl'], 
                     from_uri=request.args.get('from_uri'))

    if form.validate_on_submit():
        domain = form.domain.data
        url    = urlparse(domain)
        if url.scheme in ('http', 'https'):
            domain = '%s://%s' % (url.scheme, url.netloc)
        else:
            if len(url.netloc) == 0:
                domain = 'http://%s' % url.path
            else:
                domain = 'http://%s' % url.netloc

        authEndpoints = ninka.indieauth.discoverAuthEndpoints(domain)
        app.logger.info('form domain [%s] domain [%s] auth endpoints %d' % (form.domain.data, domain, len(authEndpoints)))

        authURL = urlparse('https://indieauth.com/auth')
        if 'authorization_endpoint' in authEndpoints:
            for url in authEndpoints['authorization_endpoint']:
                authURL = url
                break

        if authURL is not None:
            url = ParseResult(authURL.scheme, 
                              authURL.netloc,
                              authURL.path,
                              authURL.params,
                              urllib.urlencode({ 'me':            domain,
                                                 'redirect_uri':  form.redirect_uri.data,
                                                 'client_id':     form.client_id.data,
                                                 'scope':         'post',
                                                 'response_type': 'id'
                                               }),
                              authURL.fragment).geturl()

            if db is not None:
                app.logger.info('storing auth response [%s]' % domain)
                db.hset(domain, 'from_uri',     form.from_uri.data)
                db.hset(domain, 'redirect_uri', form.redirect_uri.data)
                db.hset(domain, 'client_id',    form.client_id.data)
                db.hset(domain, 'scope',        'post')
                db.hdel(domain, 'code')  # clear any existing auth code
                db.expire(domain, cfg['auth_timeout']) # expire in N minutes unless successful

            return redirect(url)
        else:
            return 'insert fancy no auth endpoint found error message here', 403

    templateData['title']         = 'Authenticate'
    templateData['form']          = form
    templateData['authed']        = False
    templateData['authed_domain'] = ''
    templateData['authed_url']    = ''
    templateData['domain_url']    = None
    templateData['domain']        = None
    templateData['from_uri']      = ''
    return render_template('login.jinja', **templateData)

@app.route('/success', methods=['GET',])
def handleLoginSuccess():
    app.logger.info('handleLoginSuccess [%s]' % request.method)
    me       = request.args.get('me')
    code     = request.args.get('code')
    scope    = None
    from_uri = None
    if db is not None:
        app.logger.info('getting data to validate auth code [%s]' % me)
        data = db.hgetall(me)
        if data:
            r = ninka.indieauth.validateAuthCode(code=code, 
                                                 client_id=data['client_id'],
                                                 redirect_uri=data['redirect_uri'])
            if 'response' in r:
                app.logger.info('login code verified')
                scope    = data['scope']
                from_uri = data['from_uri']
                token    = str(uuid.uuid4())
                db.hset(me, 'code', code)
                db.hset(me, 'token', token)
                db.expire(me, cfg['auth_timeout'])
                db.set('code-%s' % code, me)
                db.set('token-%s' % token, me)
                db.expire('code-%s' % code, cfg['auth_timeout'])

                session['indieauth_token'] = token
                session['indieauth_scope'] = scope
                session['indieauth_id']    = me
            else:
                app.logger.info('login invalid')
                clearAuth(me)
        else:
            app.logger.info('nothing found for domain [%s]' % me)

    if scope:
        if from_uri:
            return redirect(from_uri)
        else:
            return redirect('/')
    else:
        return 'authentication failed', 403

@app.route('/auth', methods=['GET',])
def handleAuth():
    app.logger.info('handleAuth [%s]' % request.method)
    result = False
    if db is not None:
        token = request.args.get('token')
        if token is not None:
            me = db.get('token-%s' % token)
            if me:
                data = db.hgetall(me)
                if data and data['token'] == token:
                    result = True
    if result:
        return 'valid', 200
    else:
        clearAuth()
        return 'invalid', 403

def domainStatus(domain):
    """Return one of the following:
      included: domain is present and not excluded
      excluded: domain is present but is excluded
      present:  domain is present but has not been claimed
    """
    result = 'absent'
    if domain is not None:
        if domain.excluded:
            result = 'excluded'
        else:
            if domain.claimed:
                result = 'included'
            else:
                result = 'present'
    return result

@app.route('/domain', methods=['GET', 'POST'])
def handleDomain():
    app.logger.info('handleDomain [%s]' % request.method)

    owner = False
    authed, indieauth_id, authed_domain, authed_url = checkAuth()

    d = request.args.get('id')
    app.logger.info('args["id"] %s' % d)
    if d is None:
        d     = indieauth_id
        owner = True
    else:
        if authed:
            d = d.lower().replace('http://', '').replace('https://', '')
            s = indieauth_id.lower().replace('http://', '').replace('https://', '')
            owner = d == s

    if d is not None:
        app.logger.info('%s %s %s %s' % (d, cfg['dataPath'], cfg['domainPath'], cfg['domains']))
        domainList = Domains(cfg['dataPath'], cfg['domainPath'], cfg['domains'])
        if d not in domainList:

            domainList[d] = Domain(d, cfg['domainPath'])
        domain = domainList[d]
        status = domainStatus(domain)
        found  = domain.found

        if not found and owner:
            domain.store()
            found = True
    else:
        found = False

    if found:
        form = DomainForm(domain=domain.domain, excluded=domain.excluded)

        if authed and owner and request.method == 'POST':
            app.logger.info('domain post')
            if form.validate():
                domain.excluded = form.excluded.data
                domain.claimed  = True
                domain.store()
                domainList.store()
                return redirect('/domain')
            else:
                flash('all fields are required')

        if not owner:
            if domain.excluded:
                templateData['caption'] = 'Domain is being excluded by request of owner.'
            else:
                if domain.claimed:
                    templateData['caption'] = 'Domain is being included.'
                else:
                    templateData['caption'] = 'Domain has not been claimed.'
        else:
            templateData['caption'] = ''

        templateData['title']         = 'Domain Details'
        templateData['form']          = form
        templateData['authed']        = authed
        templateData['authed_domain'] = authed_domain
        templateData['authed_url']    = authed_url
        templateData['owner']         = owner
        templateData['domain']        = domain.domain
        templateData['domain_url']    = domain.url
        templateData['from_uri']      = '/domain?id=%s' % domain.domain
        if domain.ts is None:
            templateData['domain_polled']    = ''
            templateData['domain_polled_ts'] = 'n/a'
        else:
            templateData['domain_polled']    = time.strftime('%Y-%m-%d %H:%M:%S', domain.ts)
            templateData['domain_polled_ts'] = time.strftime('%Y-%m-%d %H:%M:%S', domain.ts)

        return render_template('domain.jinja', **templateData)
    else:
        form = DomainNotFoundForm(domain=d)
        templateData['title']         = 'Domain not found'
        templateData['form']          = form
        templateData['domain']        = d
        templateData['authed']        = authed
        templateData['authed_domain'] = authed_domain
        templateData['authed_url']    = authed_url
        templateData['domain_url']    = ''

        if d is None:
            templateData['message']  = 'You must be logged in or specify a domain to search for'
            templateData['from_uri'] = ''
        else:
            templateData['message']  = 'Unable to find any information about %s' % d
            templateData['from_uri'] = '/domain'

        return render_template('domain-not-found.jinja', **templateData)

@app.route('/stats', methods=['GET'])
def handleStats():
    app.logger.info('handleStats [%s]' % request.method)

    d = request.args.get('domain')
    app.logger.info('args["domain"] %s' % d)
    if d is None:
        with open(os.path.join(cfg['dataPath'], 'summary.json'), 'r') as h:
            result = json.load(h)
        return jsonify(**result)
    else:
        url = urlparse(d)
        if len(url.netloc) > 0:
            domain = url.netloc
        else:
            domain = d
        statsFile = os.path.join(cfg['domainPath'], domain, 'stats_%s.json' % domain)
        if os.path.exists(statsFile):
            with open(statsFile, 'r') as h:
                result = json.load(h)
                return jsonify(**result)
        else:
            return 'unable to determine domain', 404

@app.route('/', methods=['GET'])
def handleIndex():
    app.logger.info('handleIndex [%s]' % request.method)

    authed, indieauth_id, authed_domain, authed_url = checkAuth()

    form = IndexForm()

    templateData['title']         = 'Indie-Stats'
    templateData['form']          = form
    templateData['authed']        = authed
    templateData['authed_domain'] = authed_domain
    templateData['authed_url']    = authed_url
    templateData['from_uri']      = '/'

    with open(os.path.join(cfg['dataPath'], 'summary.json'), 'r') as h:
        stats = json.load(h)
        for key in stats:
            templateData[key] = stats[key] 

    return render_template('index.jinja', **templateData)

def initLogging(logger, logpath=None, echo=False):
    logFormatter = logging.Formatter("%(asctime)s %(levelname)-9s %(message)s", "%Y-%m-%d %H:%M:%S")

    if logpath is not None:
        from logging.handlers import RotatingFileHandler

        logfilename = os.path.join(logpath, 'indie-stats.log')
        logHandler  = logging.handlers.RotatingFileHandler(logfilename, maxBytes=1024 * 1024 * 100, backupCount=7)
        logHandler.setFormatter(logFormatter)
        logger.addHandler(logHandler)

    if echo:
        echoHandler = logging.StreamHandler()
        echoHandler.setFormatter(logFormatter)
        logger.addHandler(echoHandler)

    logger.setLevel(logging.INFO)
    logger.info('starting indie-stats app')

def loadConfig(configFilename, host=None, port=None):
    filename = os.path.abspath(configFilename)

    if os.path.exists(filename):
        result = json.load(open(filename, 'r'))
    else:
        result = {}

    if host is not None and 'host' not in result:
        result['host'] = host
    if port is not None and 'port' not in result:
        result['port'] = port
    if 'auth_timeout' not in result:
        result['auth_timeout'] = 300

    return result

def getRedis(cfgRedis):
    if 'host' not in cfgRedis:
        cfgRedis['host'] = '127.0.0.1'
    if 'port' not in cfgRedis:
        cfgRedis['port'] = 6379
    if 'db' not in cfgRedis:
        cfgRedis['db'] = 0

    return redis.StrictRedis(host=cfgRedis['host'], port=cfgRedis['port'], db=cfgRedis['db'])

# event = events.Events(config={ "handler_path": os.path.join(_ourPath, "handlers") })

def buildTemplateContext(config):
    result = {}
    for key in ('baseurl', 'title', 'meta'):
        if key in config:
            value = config[key]
        else:
            value = ''
        result[key] = value
    return result

def doStart(app, configFile, ourHost=None, ourPort=None, echo=False):
    _cfg = loadConfig(configFile, host=ourHost, port=ourPort)
    _db  = None
    if 'secret' in _cfg:
        app.config['SECRET_KEY'] = _cfg['secret']
    initLogging(app.logger, _cfg['dataPath'], echo=echo)
    if 'redis' in _cfg:
        _db = getRedis(_cfg['redis'])
    return _cfg, _db

if _uwsgi:
    cfg, db = doStart(app, _configFile, _ourPath)
    templateData = buildTemplateContext(cfg)
#
# None of the below will be run for nginx + uwsgi
#
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--host',   default='0.0.0.0')
    parser.add_argument('--port',   default=5000, type=int)
    parser.add_argument('--config', default='/etc/indie-stats.cfg')

    args = parser.parse_args()

    cfg, db = doStart(app, args.config, args.host, args.port, echo=True)
    templateData = buildTemplateContext(cfg)

    app.run(host=cfg['host'], port=cfg['port'], debug=True)
