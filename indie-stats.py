#!/usr/bin/env python

"""
:copyright: (c) 2014-2015 by Mike Taylor
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

import ninka
import redis
import requests

from bearlib.config import Config
from bearlib.tools import baseDomain
from urlparse import urlparse, ParseResult
from flask import Flask, request, redirect, render_template, session, flash, jsonify

from flask.ext.wtf import Form
from wtforms import TextField, HiddenField, BooleanField
from wtforms.validators import Required
from flask_restful import reqparse, abort, Resource, Api

sys.path.append(os.path.dirname(__file__))

from domains import Domain, Domains


class LoginForm(Form):
    me           = TextField('me', validators = [ Required() ])
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
_uwsgi = __name__.startswith('uwsgi') or 'UWSGI_ORIGINAL_PROC_NAME' in os.environ.keys()
if _uwsgi:
    _ourPath = os.path.dirname(__name__.replace('uwsgi_file_', '').replace('_', '/'))
else:
    _ourPath = os.getcwd()
_configFile = os.path.join(_ourPath, 'indie-stats.cfg')

print _ourPath
print _configFile

app = Flask(__name__)
app.config['SECRET_KEY'] = 'foo'  # replaced downstream
api = Api(app)
cfg = None
db  = None

parser = reqparse.RequestParser()
parser.add_argument('domain')

class DomainList(Resource):
    def get(self):
        app.logger.info('apiDomainList')
        l = db.get('cache-domain-list')
        if l is None:
            domainList = Domains(cfg.dataPath, cfg.domainPath, cfg.domains)
            l = domainList.keys()
            db.set('cache-domain-list', json.dumps(l))
        else:
            l = json.loads(l)
        return l

    # def post(self):
    #     args = parser.parse_args()
    #     domain = args['domain']
    #     found = False
    #     domainList = os.path.join(cfg['domainPath'], 'domain_list.txt')
    #     if os.path.exists(domainList):
    #         with open(domainList, 'r') as h:
    #             for line in h.readlines():
    #                 d = line.strip().encode('utf8')
    #                 if d == domain:
    #                     found = True
    #     if not found:
    #         app.logger.info('%s not found in domain list' % domain)
    #         with open(domainList, 'a+') as h:
    #             h.write('%s\n' % domain)
    #         d = Domain(domain, cfg.domainPath)
    #         d.store()
    #         db.delete('cache-domain-list')
    #         return { "domain": domain, "result": "Domain has been added to the tracking list" }, 201
    #     else:
    #         return { "domain": domain, "result": "Domain is already being tracked" }, 200

class DomainInfo(Resource):
    def get(self, domain):
        app.logger.info('apiDomainInfo [%s]' % domain)
        d = db.get('cache-%s' % domain)
        if d is None:
            o = Domain(domain, cfg.domainPath)
            if o.found:
                d = o.asDict()
                db.set('cache-%s' % domain, json.dumps(d))
            else:
                d = None
        else:
            d = json.loads(d)
        if d is None:
            return { "domain": domain, "result": "Domain is not being tracked" }, 404
        else:
            return d, 200

api.add_resource(DomainList, '/api/v1/domains')
api.add_resource(DomainInfo, '/api/v1/domains/<domain>')


def clearAuth():
    if 'indieauth_token' in session:
        if db is not None:
            key = db.get('token-%s' % session['indieauth_token'])
            if key:
                db.delete(key)
                db.delete('token-%s' % session['indieauth_token'])
    session.pop('indieauth_token', None)
    session.pop('indieauth_scope', None)
    session.pop('indieauth_id',    None)

def checkAuth():
    authed        = False
    indieauth_id  = None
    if 'indieauth_id' in session and 'indieauth_token' in session:
        app.logger.info('session cookie found')
        indieauth_id    = session['indieauth_id']
        indieauth_token = session['indieauth_token']
        if db is not None:
            key = db.get('token-%s' % indieauth_token)
            if key:
                data = db.hgetall(key)
                if data and data['token'] == indieauth_token:
                    authed = True
    return authed, indieauth_id

def checkAccessToken(access_token):
    if access_token is not None and db is not None:
        key = db.get('token-%s' % access_token)
        if key:
            data      = key.split('-')
            me        = data[1]
            client_id = data[2]
            scope     = data[3]
            app.logger.info('access token valid [%s] [%s] [%s]' % (me, client_id, scope))
            return me, client_id, scope
    else:
        return None, None, None

@app.route('/logout', methods=['GET'])
def handleLogout():
    app.logger.info('handleLogout [%s]' % request.method)
    clearAuth()
    return redirect('/')

@app.route('/login', methods=['GET', 'POST'])
def handleLogin():
    app.logger.info('handleLogin [%s]' % request.method)

    me          = None
    redirectURI = '%s/success' % cfg.baseurl
    fromURI     = request.args.get('from_uri')
    # if fromURI is None:
    #     fromURI = '%s/login' % cfg.baseurl
    app.logger.info('redirectURI [%s] fromURI [%s]' % (redirectURI, fromURI))
    form = LoginForm(me='', 
                     client_id=cfg.client_id, 
                     redirect_uri=redirectURI, 
                     from_uri=fromURI)

    if form.validate_on_submit():
        app.logger.info('me [%s]' % form.me.data)

        me            = 'https://%s/' % baseDomain(form.me.data, includeScheme=False)
        authEndpoints = ninka.indieauth.discoverAuthEndpoints(me)

        if 'authorization_endpoint' in authEndpoints:
            authURL = None
            for url in authEndpoints['authorization_endpoint']:
                authURL = url
                break
            if authURL is not None:
                url = ParseResult(authURL.scheme, 
                                  authURL.netloc,
                                  authURL.path,
                                  authURL.params,
                                  urllib.urlencode({ 'me':            me,
                                                     'redirect_uri':  form.redirect_uri.data,
                                                     'client_id':     form.client_id.data,
                                                     'scope':         'post',
                                                     'response_type': 'id'
                                                   }),
                                  authURL.fragment).geturl()
                if db is not None:
                    key  = 'login-%s' % me
                    data = db.hgetall(key)
                    if data and 'token' in data: # clear any existing auth data
                        db.delete('token-%s' % data['token'])
                        db.hdel(key, 'token')
                    db.hset(key, 'auth_url',     ParseResult(authURL.scheme, authURL.netloc, authURL.path, '', '', '').geturl())
                    db.hset(key, 'from_uri',     form.from_uri.data)
                    db.hset(key, 'redirect_uri', form.redirect_uri.data)
                    db.hset(key, 'client_id',    form.client_id.data)
                    db.hset(key, 'scope',        'post')
                    db.expire(key, cfg.auth_timeout) # expire in N minutes unless successful
                app.logger.info('redirecting to [%s]' % url)
                return redirect(url)
        else:
            return 'insert fancy no auth endpoint found error message here', 403

    templateContext = {}
    templateContext['title'] = 'Sign In'
    templateContext['form']  = form
    return render_template('login.jinja', **templateContext)

@app.route('/success', methods=['GET',])
def handleLoginSuccess():
    app.logger.info('handleLoginSuccess [%s]' % request.method)
    scope = None
    me    = request.args.get('me')
    code  = request.args.get('code')
    app.logger.info('me [%s] code [%s]' % (me, code))

    if db is not None:
        app.logger.info('getting data to validate auth code')
        key  = 'login-%s' % me
        data = db.hgetall(key)
        if data:
            app.logger.info('calling [%s] to validate code' % data['auth_url'])
            r = ninka.indieauth.validateAuthCode(code=code, 
                                                 client_id=data['client_id'],
                                                 redirect_uri=data['redirect_uri'],
                                                 validationEndpoint=data['auth_url'])
            if r['status'] == requests.codes.ok:
                app.logger.info('login code verified')
                if 'scope' in r['response']:
                    scope = r['response']['scope']
                else:
                    scope = data['scope']
                from_uri = data['from_uri']
                token    = str(uuid.uuid4())

                db.hset(key, 'code',  code)
                db.hset(key, 'token', token)
                db.expire(key, cfg['auth_timeout'])
                db.set('token-%s' % token, key)
                db.expire('token-%s' % code, cfg['auth_timeout'])

                session['indieauth_token'] = token
                session['indieauth_scope'] = scope
                session['indieauth_id']    = me
            else:
                app.logger.info('login invalid')
                clearAuth()
        else:
            app.logger.info('nothing found for [%s]' % me)

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

@app.route('/token', methods=['POST', 'GET'])
def handleToken():
    app.logger.info('handleToken [%s]' % request.method)

    if request.method == 'GET':
        access_token = request.headers.get('Authorization')
        if access_token:
            access_token = access_token.replace('Bearer ', '')
        else:
            access_token 
        me, client_id, scope = checkAccessToken(access_token)

        if me is None or client_id is None:
            return ('Token is not valid', 400, {})
        else:
            params = { 'me':        me,
                       'client_id': client_id,
                     }
            if scope is not None:
                params['scope'] = scope
            return (urllib.urlencode(params), 200, {'Content-Type': 'application/x-www-form-urlencoded'})

    elif request.method == 'POST':
        code         = request.form.get('code')
        me           = request.form.get('me')
        redirect_uri = request.form.get('redirect_uri')
        client_id    = request.form.get('client_id')
        state        = request.form.get('state')

        app.logger.info('    code         [%s]' % code)
        app.logger.info('    me           [%s]' % me)
        app.logger.info('    client_id    [%s]' % client_id)
        app.logger.info('    state        [%s]' % state)
        app.logger.info('    redirect_uri [%s]' % redirect_uri)

        # r = ninka.indieauth.validateAuthCode(code=code, 
        #                                      client_id=me,
        #                                      state=state,
        #                                      redirect_uri=redirect_uri)
        r = validateAuthCode(code=code, 
                                             client_id=me,
                                             state=state,
                                             redirect_uri=redirect_uri)
        if r['status'] == requests.codes.ok:
            app.logger.info('token request auth code verified')
            scope = r['response']['scope']
            key   = 'app-%s-%s-%s' % (me, client_id, scope)
            token = db.get(key)
            if token is None:
                token     = str(uuid.uuid4())
                token_key = 'token-%s' % token
                db.set(key, token)
                db.set(token_key, key)

            app.logger.info('  token generated for [%s] : [%s]' % (key, token))

            params = { 'me': me,
                       'scope': scope,
                       'access_token': token
                     }
            return (urllib.urlencode(params), 200, {'Content-Type': 'application/x-www-form-urlencoded'})

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
    app.logger.info('handleInfo [%s]' % request.method)

    owner = False
    authed_domain = None
    authed, indieauth_id = checkAuth()
    app.logger.info('[%s] [%s]' % (authed, indieauth_id))
    arg_domain = request.args.get('domain')
    app.logger.info('args["domain"] %s' % arg_domain)

    if authed:
        authed_url = urlparse(indieauth_id)
        authed_domain = authed_url.netloc
        if arg_domain is None:
            arg_domain = authed_domain
        owner = arg_domain == authed_domain

    if arg_domain is not None:
        app.logger.info('%s %s %s %s' % (arg_domain, cfg.dataPath, cfg.domainPath, cfg.domains))
        # domainList = Domains(cfg.dataPath, cfg.domainPath, cfg.domains)
        # if arg_domain not in domainList:
        #     domainList[arg_domain] = Domain(arg_domain, cfg.domainPath)
        # domain = domainList[arg_domain]
        domain = Domain(arg_domain, cfg.domainPath)
        status = domainStatus(domain)
        found  = domain.found

        if not found and owner:
            domain.store()
            found = True
    else:
        found = False

    templateContext = {}

    if found:
        form = DomainForm(domain=domain.domain, excluded=domain.excluded)

        if authed and owner and request.method == 'POST':
            app.logger.info('domain post')
            if form.validate():
                domain.excluded = form.excluded.data
                domain.claimed  = True
                domain.store()
                return redirect('/domain')
            else:
                flash('all fields are required')

        if not owner:
            if domain.excluded:
                templateContext['caption'] = 'Domain is being excluded by request of owner.'
            else:
                if domain.claimed:
                    templateContext['caption'] = 'Domain is being included.'
                else:
                    templateContext['caption'] = 'Domain has not been claimed.'
        else:
            templateContext['caption'] = ''

        templateContext['title']         = 'Domain Information'
        templateContext['form']          = form
        templateContext['authed']        = authed
        templateContext['authed_domain'] = authed_domain
        templateContext['authed_url']    = indieauth_id
        templateContext['owner']         = owner
        templateContext['domain']        = domain.domain
        templateContext['domain_url']    = domain.url
        templateContext['from_uri']      = '/domain?domain=%s' % domain.domain
        if domain.ts is None:
            templateContext['domain_polled']    = ''
            templateContext['domain_polled_ts'] = 'n/a'
        else:
            templateContext['domain_polled']    = time.strftime('%Y-%m-%d %H:%M:%S', domain.ts)
            templateContext['domain_polled_ts'] = time.strftime('%Y-%m-%d %H:%M:%S', domain.ts)

        return render_template('domain.jinja', **templateContext)
    else:
        form = DomainNotFoundForm(domain=arg_domain)
        templateContext['title']         = 'Domain not found'
        templateContext['form']          = form
        templateContext['domain']        = arg_domain
        templateContext['authed']        = authed
        templateContext['authed_domain'] = authed_domain
        templateContext['authed_url']    = indieauth_id
        templateContext['domain_url']    = ''

        if arg_domain is None:
            templateContext['message']  = 'You must be logged in or specify include a domain parameter to search for'
            templateContext['from_uri'] = ''
        else:
            templateContext['message']  = 'Unable to find any information about %s' % arg_domain
            templateContext['from_uri'] = '/domain'

        return render_template('domain-not-found.jinja', **templateContext)

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

    authed, indieauth_id = checkAuth()
    app.logger.info('[%s] [%s]' % (authed, indieauth_id))

    form = IndexForm()

    templateContext = {}
    templateContext['title']         = 'Indie-Stats'
    templateContext['form']          = form
    templateContext['authed']        = authed
    templateContext['authed_domain'] = indieauth_id
    templateContext['authed_url']    = indieauth_id
    templateContext['from_uri']      = '/'

    with open(os.path.join(cfg.dataPath, 'summary.json'), 'r') as h:
        stats = json.load(h)
        for key in stats:
            templateContext[key] = stats[key] 

    return render_template('index.jinja', **templateContext)

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

def loadConfig(configFilename, host=None, port=None, logpath=None):
    result = Config()
    result.fromJson(configFilename)

    if host is not None:
        result.host = host
    if port is not None:
        result.port = port
    if logpath is not None:
        result.paths.log = logpath
    if 'auth_timeout' not in result:
        result.auth_timeout = 300
    return result

def getRedis(config):
    if 'host' not in config:
        config.host = '127.0.0.1'
    if 'port' not in config:
        config.port = 6379
    if 'db' not in config:
        config.db = 0
    return redis.StrictRedis(host=config.host, port=config.port, db=config.db)

def doStart(app, configFile, ourHost=None, ourPort=None, ourPath=None, echo=False):
    _cfg = loadConfig(configFile, host=ourHost, port=ourPort, logpath=ourPath)
    _db  = None
    if 'secret' in _cfg:
        app.config['SECRET_KEY'] = _cfg.secret
    initLogging(app.logger, _cfg.paths.log, echo=echo)
    if 'redis' in _cfg:
        _db = getRedis(_cfg.redis)
    app.logger.info('configuration loaded from %s' % configFile)
    return _cfg, _db

if _uwsgi:
    cfg, db = doStart(app, _configFile, echo=True)
#
# None of the below will be run for nginx + uwsgi
#
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--host',   default='0.0.0.0')
    parser.add_argument('--port',   default=5000, type=int)
    parser.add_argument('--logpath',  default='.')
    parser.add_argument('--config', default='/etc/indie-stats.cfg')

    args = parser.parse_args()

    cfg, db = doStart(app, args.config, args.host, args.port, args.logpath, echo=True)

    app.run(host=cfg.host, port=cfg.port, debug=True)
