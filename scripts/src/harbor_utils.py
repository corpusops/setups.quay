#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import datetime

import os
import json
from collections import OrderedDict
import requests
import logging
import copy
import secrets
import re
import smtplib
from http.client import HTTPConnection
from email.mime.text import MIMEText


def as_bool(value):
    if isinstance(value, str):
        return bool(re.match("^(y|o|1|t)", value.lower()))
    else:
        return bool(value)


L = logging.getLogger(__name__)
DEFAULT_ACCESS = [
    {'action': 'push', 'resource': 'repository'},
    {'action': 'pull', 'resource': 'repository'},
    {'action': 'delete', 'resource': 'artifact'},
    {'action': 'read', 'resource': 'helm-chart'},
    {'action': 'create', 'resource': 'helm-chart-version'},
    {'action': 'delete', 'resource': 'helm-chart-version'},
    {'action': 'create', 'resource': 'tag'},
    {'action': 'delete', 'resource': 'tag'},
    {'action': 'create', 'resource': 'artifact-label'},
    {'action': 'create', 'resource': 'scan'}]
ZERO_ACCESS = [{'action': 'read', 'resource': 'tag'}]
ZERO_PERMISSIONS = {
    'access': ZERO_ACCESS,
    'kind': 'project',
    'namespace': "library"}
DEFAULT_ROBOT_PERMISSION = {
    'access': DEFAULT_ACCESS,
    'kind': 'project',
    'namespace': None}
DEFAULT_ROBOT = {
    'disable': False,
    'duration': -1,
    'editable': True,
    'expires_at': -1,
    'id': 5,
    'level': 'system',
    'name': 'bot__project+testrobot',
    'permissions': [],
}
QUAY_DATAFILE = os.environ.get("QUAYR_DATAFILE_JSON", "data/quay.json")


default = object()
_vars = {}

EXPORTFILE = '/w/data/portus.json'
PORTUS_URL = os.environ.get('PORTUS_URL', '')
PORTUS_API = '/api/v1'

QUAY_URL = os.environ.get('QUAY_URL', '')
QUAY_API = '/api/v2.0'

# do not export from portugs tags that may look like a SHA8
PTAGS = 'prod|dev|staging|qa|latest|:.*[-_.]+'
PORTUS_TAGS_WHITELIST = re.compile(os.environ.get(
    'PORTUS_TAGS_WHITELIST', PTAGS), flags=re.M | re.I)
PORTUS_TAGS_FILTER = re.compile(os.environ.get(
    'PORTUS_TAGS_FILTER', ':[^-_.]{8}$'), flags=re.M | re.I)
PORTUS_TOKEN = os.environ.get('PORTUS_TOKEN', '')
QUAY_COOKIE = os.environ.get('QUAY_COOKIE', '').strip()
QUAY_USERNAME = os.environ.get('QUAY_USERNAME', '').strip()
QUAY_PASSWORD = os.environ.get('QUAY_PASSWORD', '').strip()
# if QUAY_COOKIE:
#     QUAY_COOKIE = base64.b64decode(QUAY_COOKIE).decode().strip()

LOGLEVEL = os.environ.get("LOGLEVEL", "info").upper()
MAIL_LANG = os.environ.get("MAILLANG", "fr")
REQUEST_DEBUG = as_bool(os.environ.get("REQUEST_DEBUG", ""))
MAIL_TEMPLATES = {
    "subject": {
        "en": "Your quay access ({server})",
        "fr": "Votre accès quay ({server})",
    },
    "mail": {
        "en": """\
Hi,
You can connect to {server}
    login: {login}
    password: {password}  (valid if you didn't changed it)
Thx to reinit your password upon first connection
Thx,
Harbor team
""",
        "fr": """\
Bonjour,
Vous pouvez vous connecter à {server}
    login: {login}
    password: {password} (valide si vous ne l'avez pas changer)
Merci de réinitialiser votre mot de passe à la première connexion.
Cordialement,
Équipe quay
""",
    },
}


def filter_dict(d, filters=None):
    if filters is None:
        filters = [a for a in d]
    ret = {}
    for i in d:
        if i not in filters:
            continue
        ret[i] = d[i]
    return ret


def toggle_debug(activate=None, loglevel=None, debuglevel=logging.DEBUG, errorlevel=logging.INFO):
    if loglevel is None:
        loglevel = LOGLEVEL
    loglevel = loglevel.upper()
    if activate is None:
        activate = not _vars["debug"]
    dl = debuglevel <= logging.DEBUG and 1 or 0
    lvl = activate and debuglevel or errorlevel
    HTTPConnection.debuglevel = dl
    for req_log in [
        logging.getLogger(lg) for lg in (
            "urllib3",
            "urllib3.connectionpool",
            "equests.packages.urllib3",
        )
    ]:
        req_log.propagate = activate
        req_log.setLevel(lvl)
    _vars["debug"] = activate
    logging.getLogger("").setLevel(loglevel)
    return activate


def setup_logging(loglevel=None):
    logging.basicConfig()
    debuglvl = REQUEST_DEBUG and logging.DEBUG or logging.INFO
    toggle_debug(True, debuglevel=debuglvl, loglevel=loglevel)


def quay_api(path,
               method='get',
               json=default,
               force_uri=False,
               force_url=False,
               userheaders=default,
               *a, **kw):
    """
    to auth yourself, login in a quay session with your user
    and sneak the requests to /apî,
    and grab the value of cookies which must look like "_gorilla_crsf=xxx, sid=xxxx"
    export it ao $QUAY_COOKIE env var
    """
    if userheaders is default:
        userheaders = get_userheaders()
    url = (not force_url) and QUAY_URL or ''
    uri = (not force_uri) and QUAY_API or ''
    uri = url + uri + path
    if json is not default:
        kw['json'] = json
    headers = kw.setdefault('headers', {})
    if isinstance(userheaders, dict):
        _ = [headers.setdefault(h, v) for h, v, in userheaders.items()]
    if QUAY_COOKIE:
        headers.setdefault('Cookie', QUAY_COOKIE)
    else:
        kw['auth'] = (QUAY_USERNAME, QUAY_PASSWORD)
    return getattr(requests, method.lower())(uri, *a, **kw)


def ensure_quay_connected():
    user = quay_api('/users/current')
    assert user.status_code == 200
    return user.json()


def get_userheaders(userheaders=None):
    if userheaders is None:
        try:
            userheaders = _vars['userheaders']
        except KeyError:
            userheaders = _vars['userheaders'] = filter_dict(
                quay_api('/users/current', userheaders=None).headers,
                ['X-Harbor-Csrf-Token', 'X-Request-Id'])
    return userheaders


def portus_api(path, method='get', json=default, force_uri=False, force_url=False, *a, **kw):
    url = (not force_url) and PORTUS_URL or ''
    uri = (not force_uri) and PORTUS_API or ''
    uri = url + uri + path
    if json is not default:
        kw['json'] = json
    headers = kw.setdefault('headers', {})
    headers.setdefault('Portus-Auth', f'{PORTUS_TOKEN}')
    return getattr(requests, method.lower())(uri, *a, **kw)


def save(export, fp=EXPORTFILE):
    with open(fp, 'w') as f:
        json.dump(export, f, indent=2)


def load_portus(exportfile=EXPORTFILE):
    try:
        with open(exportfile, 'r') as f:
            export = json.load(f)
    except FileNotFoundError:
        export = {}
    return export


def get_username(item):
    un = item['username']
    if item['bot']:
        un = f'bot__{un}'
    return un


def setup(load=True, exportfile=EXPORTFILE, loglevel=None):
    export = None
    setup_logging(loglevel=None)
    if load:
        export = load_portus(exportfile)
    return export


def toggle_requests_debug(toggle=True):
    # These two lines enable debugging at httplib level (requests->urllib3->http.client)
    # You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
    # The only thing missing will be the response.body which is not logged.
    level = {
        True: logging.DEBUG,
        False: logging.ERROR,
    }[toggle]
    try:
        import http.client as http_client
    except ImportError:
        # Python 2
        import httplib as http_client
    http_client.HTTPConnection.debuglevel = toggle and 1 or 0
    # You must initialize logging, otherwise you'll not see debug output.
    logging.getLogger().setLevel(level)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(level)
    requests_log.propagate = True


def get_quay_batched(uri, olddata=None, *a, **kw):
    if olddata is None:
        uri = QUAY_API + uri
        kw['force_uri'] = True
    ret = quay_api(uri, *a, **kw)
    data = ret.json()
    if olddata is None:
        olddata = data
    else:
        if isinstance(data, dict):
            for i, v in data.items():
                olddata[i] = v
        elif isinstance(data, list):
            for i in data:
                olddata.append(i)
        elif isinstance(data, tuple):
            for i in data:
                olddata = olddata + data
        elif isinstance(data, set):
            for i in data:
                olddata.add(i)
        else:
            return data
        data = olddata
    try:
        for link in requests.utils.parse_header_links(ret.headers['Link']):
            if link['rel'] == 'next':
                data = get_quay_batched(link['url'], olddata=data, *a, **kw)
    except KeyError:
        pass
    return data


def create_robot(user, prefix='bot__', projects=None, **kw):
    projects = projects or []
    bot = copy.deepcopy(DEFAULT_ROBOT)
    bot['name'] = user.startswith(prefix) and user[len(prefix):]
    for p in projects:
        perm = p
        if not isinstance(perm, dict):
            perm = copy.deepcopy(DEFAULT_ROBOT_PERMISSION)
            perm['namespace'] = p
        bot['permissions'].append(perm)
    bot.update(**kw)
    ret = quay_api('/robots', method='post', json=bot)
    assert ret.status_code == 201
    robot = quay_api(ret.headers['Location'], force_uri=True).json()
    return robot


def update_robot_secret(robot, secret):
    if secret:
        ret = quay_api(
            f'/robots/{robot["id"]}', method='patch', json={'secret': secret})
        assert ret.status_code == 200
        L.info(f'Updated secret for {robot["name"]}')


def get_or_create_robot(user, granted_namespaces=None, robots=None, namespaces=None, secret=None):
    if granted_namespaces is None:
        granted_namespaces = []
    if robots is None:
        robots = OrderedDict([(a['name'], a) for a in get_quay_batched('/robots')])
    if namespaces is None:
        namespaces = OrderedDict([(a['name'], a) for a in get_quay_batched('/projects')])
    try:
        robot = robots[user]
    except KeyError:
        projects = [a for a in granted_namespaces if a in namespaces]
        if projects:
            permissions = []
        else:
            permissions = [ZERO_PERMISSIONS.copy()]
        robot = robots[user] = create_robot(user, projects=projects, permissions=permissions)
        L.info(f'Created robot: {user}')
    if secret:
        update_robot_secret(robot, secret)
    return robot


def sortperm(perm):
    return list(sorted([f'{a["action"]}__{a["resource"]}' for a in perm]))


def equivalent_permissions(perma, permb):
    return sortperm(perma) == sortperm(permb)


def get_quay_data(quaydatafile=QUAY_DATAFILE):
    try:
        d = _vars['quaydata']
        assert d
    except (KeyError, AssertionError):
        pass
    if not os.path.exists(quaydatafile):
        write_quay_data({}, quaydatafile)
    with open(quaydatafile) as fic:
        d = _vars['quaydata'] = json.load(fic)
    return d


def write_quay_data(data=None, quaydatafile=QUAY_DATAFILE):
    if data is None:
        data = get_quay_data(quaydatafile=quaydatafile)
    with open(quaydatafile, "w") as fic:
        json.dump(data, fic, indent=2, sort_keys=True)


def get_quay_login(login, quaydatafile=QUAY_DATAFILE, password_length=16):
    data = get_quay_data(quaydatafile=quaydatafile)
    opassword = data.get(login, {}).get('password', '')
    try:
        password = data[login]["password"]
        assert password
    except (KeyError, AssertionError):
        password = secrets.token_hex(password_length)
        password = f'{password[:8].upper()}{password[8:]}'
        data.setdefault(login, {})["password"] = password
    write = opassword != password
    if write:
        write_quay_data(data)
    return data[login]


def get_quay_login_password(login, quaydatafile=QUAY_DATAFILE):
    return get_quay_login(login, quaydatafile)['password']


def get_or_create_user(login, udata=None, password=None, email=None, quaydatafile=QUAY_DATAFILE,
                       change_password=False):
    data = get_quay_data(quaydatafile)
    if udata is None:
        udata = get_quay_login(login, quaydatafile=quaydatafile)
    write = False
    for i in ['email', 'password']:
        lval = locals()[i]
        if lval and (lval != udata.get(i, '')):
            udata[i] = lval
            write = True
    if write:
        data[login] = udata
        write_quay_data(data)
    email, password = udata['email'], udata['password']
    users = dict([(a['username'], a) for a in get_quay_batched('/users')])
    try:
        user = users[login]
        if change_password:
            ret = quay_api(
                f'/users/{user["user_id"]}/password', method='put',
                json={'new_password': password})
            assert ret.status_code == 200
    except KeyError:
        L.info(f'Created user: {login}')
        ret = quay_api(
            '/users', method='post',
            json={"username": login,
                  "realname": login,
                  "email": email,
                  "password": password})
        assert ret.status_code == 201
        user = quay_api(ret.headers['Location'], force_uri=True).json()
    user['password'] = password
    return user


def notify_access(
    user,
    mail_lang,
    tls,
    dry_run,
    mail_server,
    mail_port,
    mail_login,
    mail_from,
    mail_pw,
):
    subject = f"Your quay {QUAY_URL} access"
    login = user['username']
    email = user['email']
    infos = dict(
        server=QUAY_URL,
        login=login,
        password=user['password'],
    )
    text = MAIL_TEMPLATES["mail"][mail_lang].format(**infos)
    subject = MAIL_TEMPLATES["subject"][mail_lang].format(**infos)
    msg = MIMEText(text)
    date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M +0000")
    msg["From"] = mail_from
    msg["To"] = email
    msg["Date"] = date
    msg["Subject"] = subject
    if dry_run:
        L.info(f"Would send {mail_from} -> {email}")
        L.info(msg.as_string())
        L.info(f"\n\n-- PLAINTEXT --:\n{text}")
    else:
        s = smtplib.SMTP(mail_server, int(mail_port))
        s.set_debuglevel(1)
        if tls:
            s.starttls()
        if mail_login:
            s.login(mail_login, mail_pw)
        s.sendmail(mail_from, [email], msg.as_string())
        s.quit()
    return msg
# vim:set et sts=4 ts=4 tw=120:
