
import operator
import os
import re
from collections import Counter

import nltk
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from rq import Queue
from rq.job import Job

from stop_words import stops
from worker import conn

app = Flask(__name__)

env_config = os.getenv("APP_SETTINGS", "config.DevelopmentConfig")
app.config.from_object(env_config)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
# to add db command to flask instead of manage.py
migrate = Migrate(app, db)
q = Queue('wordcount', connection=conn)

from models import *  # nopep8


def count_and_save_words(url):

    errors = []

    try:
        r = requests.get(url)
    except:
        errors.append(
            "Unable to get URL. Please make sure it's valid and try again."
        )
        return {"error": errors}

    # text processing
    raw = BeautifulSoup(r.text).get_text()
    nltk.data.path.append('./nltk_data/')  # set the path
    tokens = nltk.word_tokenize(raw)
    text = nltk.Text(tokens)

    # remove punctuation, count raw words
    nonPunct = re.compile('.*[A-Za-z].*')
    raw_words = [w for w in text if nonPunct.match(w)]
    raw_word_count = Counter(raw_words)

    # stop words
    no_stop_words = [w for w in raw_words if w.lower() not in stops]
    no_stop_words_count = Counter(no_stop_words)

    # save the results
    import json
    print('----')
    print(url)
    print(json.dumps(raw_word_count))
    print(json.dumps(no_stop_words_count))
    try:
        result = Result(
            url=url,
            result_all=raw_word_count,
            result_no_stop_words=no_stop_words_count
        )
        db.session.add(result)
        db.session.commit()
        return result.id
    except Exception as e:
        print(e)
        errors.append("Unable to add item to database.")
        return {"error": errors}


@app.route('/', methods=['GET', 'POST'])
def index():
    results = {}
    if request.method == "POST":
        # # this import solves a rq bug which currently exists
        from app import count_and_save_words

        # get url that the person has entered
        url = request.form['url']
        if not url[:8].startswith(('https://', 'http://')):
            url = 'http://' + url
        job = q.enqueue_call(
            func=count_and_save_words, args=(url,), result_ttl=5000
        )
        print(job.get_id())

    return render_template('index.html', results=results)


@app.route("/results/<job_key>", methods=['GET'])
def get_results(job_key):

    job = Job.fetch(job_key, connection=conn)

    if job.is_finished:
        result = Result.query.filter_by(id=job.result).first()
        results = sorted(
            result.result_no_stop_words.items(),
            key=operator.itemgetter(1),
            reverse=True
        )[:10]
        return jsonify(results)
    else:
        return "Nay!", 202


if __name__ == '__main__':
    app.run()
