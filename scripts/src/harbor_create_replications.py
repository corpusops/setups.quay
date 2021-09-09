#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import json
import os
import sys
import copy

import click


from portus_export import export_tags
from quay_utils import (
    # noqa
    OrderedDict,
    filter_dict,
    setup_logging,
    quay_api,
    EXPORTFILE,
    DEFAULT_ROBOT_PERMISSION,
    DEFAULT_ROBOT,
    get_username,
    get_quay_batched as get_batched,
    default,
    setup,
    create_robot,
    update_robot_secret,
    ensure_quay_connected,
    get_or_create_robot,
    L)


CRON_PERIODICITY = '0 */60 * * * *'
default_repl = {
    'dest_namespace_replace_count': 1,
    'dest_namespace': 'XXX',
    'dest_registry': {'id': 0, 'name': 'Local'},
    'enabled': True,
    'filters': [{'type': 'name', 'value': 'XXX/YYY'}],
    'id': None,
    'name': 'XXX-YYY',
    'src_registry': {'id': 1, 'name': 'remote_reg'},
    'trigger': {'trigger_settings': {'cron': CRON_PERIODICITY}, 'type': 'scheduled'}
}


def get_batches(tags, length=400, separator=',', batches=None):
    if batches is None:
        batches = []

    if len(tags) >= length:
        nchars = []
        nextbatch = tags[length:]
        tags = tags[:length]
        for ix, c in enumerate(reversed(tags[:length])):
            if c == separator:
                batches.append(tags[:-(ix + 1)])
                get_batches(''.join(nchars) + nextbatch, batches=batches)
                break
            else:
                nchars.insert(0, c)
    else:
        batches.append(tags)
    return batches


@click.option("--syncregname", default=os.environ.get("SYNC_REG_NAME", "portus"))
@click.option("--cron", default=os.environ.get("SYNC_CRON", CRON_PERIODICITY))
@click.command()
def main(syncregname, cron):
    export = setup(exportfile=EXPORTFILE)
    current_user = ensure_quay_connected()  # noqa
    namespaces = OrderedDict([(a['name'], a) for a in get_batched('/projects')])
    if not namespaces:
        raise Exception('not connected')
    namespaces = OrderedDict([(a['name'], a) for a in get_batched('/projects')])
    if not namespaces:
        raise Exception('not connected')
    replications = OrderedDict([(a['name'], a) for a in get_batched('/replication/policies')])
    registries = OrderedDict([(a['name'], a) for a in get_batched('/registries')])
    registry = registries[syncregname]

    # create robots
    errors = []
    for img, idata in sorted(export['images'].items()):
        try:
            ns = namespaces[idata['namespace']]
        except KeyError:
            errors.append(f"{idata['namespace']} ns does not exists")
            continue
        img = idata['full_name']
        # if 'lck' not in img:
        #     continue
        replname_default = img.replace('/', '-')
        tags = ','.join(list(sorted(idata['tags'])))
        # but replication rules with filter strings limited to 400 chars
        # (current interface limit of quay)
        batches = get_batches(tags)
        for ix, tags in enumerate(batches):
            replname = ix == 0 and replname_default or f'{replname_default}-{ix}'
            repl_data = {'src_registry': registry,
                         'name': replname,
                         'override': True,
                         'enabled': True,
                         'trigger': {'trigger_settings': {'cron': cron},
                                     'type': 'scheduled'},
                         'filters': [{'type': 'name', 'value': img},
                                     {'type': 'tag', 'value': '{' + tags + '}'}],
                         'dest_namespace': ns['name']}
            add_replication_rule(replications, errors, ns, img, replname, repl_data)
    if errors:
        for i in errors:
            L.error(i)
        sys.exit(1)


def add_replication_rule(replications, errors, ns, img, replname, repl_data):
    try:
        repl = replications[replname]
    except KeyError:
        rdata = copy.deepcopy(default_repl)
        rdata.update(repl_data)
        ret = quay_api('/replication/policies', method='post', json=rdata)
        assert ret.status_code == 201

        repl = quay_api(ret.headers['Location'], force_uri=True).json()
        replications[repl['name']] = repl
        L.info(f"Added replication {repl['name']}")
    for i, v in repl_data.items():
        try:
            if not repl['enabled']:
                L.info("Skip {repl['name']} as it is not updated")
                break
        except KeyError:
            pass
        if repl.get(i) != v:
            L.info(f"Updating replication {repl['name']}")
            repl.update(repl_data)
            ret = quay_api(f'/replication/policies/{repl["id"]}', method='put', json=repl)
            try:
                assert ret.status_code == 200
            except AssertionError:
                raise
            else:
                repl = quay_api(f'/replication/policies/{repl["id"]}').json()
                replications[repl['name']] = repl
            break
        execs = [a for a in get_batched('/replication/executions',
                                        params={'policy_id': repl['id']})]
        if repl.get('enabled') and not execs:
            L.info(f"Starting replication {repl['name']}")
            ret = quay_api("/replication/executions", method='post',
                             json={'policy_id': repl['id']})
            assert ret.status_code == 201



if __name__ == "__main__":
    main()

# vim:set et sts=4 ts=4 tw=120:
