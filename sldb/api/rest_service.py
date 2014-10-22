import argparse
import json
import math

from flask import Flask, Response, request, jsonify
import flask.ext.sqlalchemy
import flask.ext.restless

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

import sldb.api.queries as queries
from sldb.common.models import *

app = flask.Flask(__name__)


def _add_cors_header(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET'
    response.headers['Access-Control-Allow-Headers'] = (
        'Origin, X-Requested-With, Content-Type, Accept')
    response.headers['Access-Control-Allow-Credentials'] = 'true'

    return response


def _get_paging():
    page = request.args.get('page') or 1
    per_page = request.args.get('per_page') or 10
    page = int(page)
    per_page = int(per_page)
    return page, per_page


def _split(ids, delim=','):
    return map(int, ids.split(delim))


@app.route('/api/clones/', methods=['GET'])
def clones():
    session = scoped_session(session_factory)()
    clones = queries.get_all_clones(session, _get_paging())
    session.close()
    return jsonify(objects=clones)


@app.route('/api/clone_compare/<uids>', methods=['GET'])
def clone_compare(uids):
    session = scoped_session(session_factory)()
    clones_and_samples = []
    for u in uids.split():
        clones_and_samples.append(_split(u, '_'))
    clones = queries.compare_clones(session, clones_and_samples)
    session.close()
    return jsonify(clones=clones)


@app.route('/api/clone_overlap/<filter_type>/<samples>', methods=['GET'])
def clone_overlap(filter_type, samples):
    session = scoped_session(session_factory)()
    items, num_pages = queries.get_clone_overlap(
        session, filter_type, _split(samples), _get_paging())
    session.close()
    return jsonify(items=items, num_pages=num_pages)


@app.route('/api/data/clone_overlap/<filter_type>/<samples>', methods=['GET'])
def download_clone_overlap(filter_type, samples):
    session = scoped_session(session_factory)()
    data = queries.get_clone_overlap(session, filter_type, _split(samples))
    session.close()

    def _gen(data):
        yield ','.join(['samples', 'copy_number', 'v_gene', 'j_gene',
                       'cdr3']) + '\n'
        for c in data:
            yield ','.join(map(str, [c['samples'].replace(',', ' '),
                           c['copy_number'],
                           c['clone']['v_gene'],
                           c['clone']['j_gene'],
                           c['clone']['cdr3']])) + '\n'

    return Response(_gen(data), headers={
        'Content-Disposition':
        'attachment;filename={}_{}.csv'.format(
            filter_type,
            samples.replace(',', '-'))})


@app.route('/api/v_usage/<filter_type>/<samples>', methods=['GET'])
def v_usage(filter_type, samples):
    session = scoped_session(session_factory)()
    data, headers = queries.get_v_usage(session, filter_type, _split(samples))
    session.close()
    x_categories = headers
    y_categories = data.keys()

    array = []
    for j, y in enumerate(y_categories):
        s = 0
        for i, x in enumerate(x_categories):
            usage_for_y = data[y]
            if x in usage_for_y:
                array.append([i, j, usage_for_y[x]])
                s += usage_for_y[x]
            else:
                array.append([i, j, 0])

    return jsonify(x_categories=x_categories,
                   y_categories=y_categories,
                   data=array)


@app.route('/api/data/v_usage/<filter_type>/<samples>', methods=['GET'])
def download_v_usage(filter_type, samples):
    session = scoped_session(session_factory)()
    data, headers = queries.get_v_usage(session, filter_type, _split(samples))
    session.close()
    ret = 'sample,' + ','.join(headers) + '\n'
    for sample, dist in data.iteritems():
        row = [sample]
        for gene in headers:
            if gene in dist:
                row.append(dist[gene])
            else:
                row.append(0)
        ret += ','.join(map(str, row)) + '\n'

    return Response(ret, headers={
        'Content-Disposition':
        'attachment;filename=v_usage-{}_{}.csv'.format(
            filter_type,
            samples.replace(',', '-'))})


def init_db(host, user, pw, db):
    engine = create_engine(('mysql://{}:{}@{}/'
                            '{}?charset=utf8&use_unicode=0').format(
                                user, pw, host, db))

    Base.metadata.create_all(engine)
    Base.metadata.bind = engine
    global session_factory
    session_factory = sessionmaker(bind=engine)


def run_rest_service():
    parser = argparse.ArgumentParser(
        description='Provides a restless interface to the master table '
                    'database')
    parser.add_argument('host', help='mySQL host')
    parser.add_argument('db', help='mySQL database')
    parser.add_argument('user', help='mySQL user')
    parser.add_argument('pw', help='mySQL password')
    parser.add_argument('-p', default=5000, type=int, help='API offer port')
    args = parser.parse_args()

    app.config['SQLALCHEMY_DATABASE_URI'] = (
        'mysql://{}:{}@localhost/'
        '{}?charset=utf8&use_unicode=0').format(args.user, args.pw, args.db)
    db = flask.ext.sqlalchemy.SQLAlchemy(app)

    manager = flask.ext.restless.APIManager(app, flask_sqlalchemy_db=db)

    manager.create_api(Study, methods=['GET'])
    manager.create_api(Sample, methods=['GET'], include_columns=[
                       'id', 'name', 'info', 'study'])
    manager.create_api(Sequence, methods=['GET'])
    manager.create_api(SampleStats, methods=['GET'], collection_name='stats',
                       max_results_per_page=10000,
                       results_per_page=10000)
    manager.create_api(CloneFrequency, methods=['GET'],
                       collection_name='clone_freqs',
                       exclude_columns=['sample'])
    init_db(args.host, args.user, args.pw, args.db)

    app.after_request(_add_cors_header)
    app.run(host='0.0.0.0', port=args.p, debug=True, threaded=True)
