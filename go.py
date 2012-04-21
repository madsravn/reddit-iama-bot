#!/usr/bin/python

import os
import sys
import time
import narwal
import pymongo
import urlparse


USERNAME = os.environ['REDDIT_USERNAME']
PASSWORD = os.environ['REDDIT_PASSWORD']
MONGO_URI = os.environ['MONGOLAB_URI']
DB_NAME = urlparse.urlparse(MONGO_URI).path.strip('/')

MIN_COMMENTS = 150
HEADER_FORMAT = (
  u'Most (if not all) of the answers from [{host}](/user/{host}/) (updated: {last_updated}):\n\n'
  u'*****\n'
)
SECOND_HEADER_FORMAT = (
  u'(page {})\n\n'
  u'*****\n'
)
QA_FORMAT = (
  u'**[Question]({qlink}?context=1) ({asker}):**\n\n'
  u'{question}\n\n'
  u'**[Answer]({alink}?context=1) ({host}):**\n\n'
  u'{answer}\n\n'
  u'*****\n'
)
TOP_FORMAT = (
  u'**Top-level Comment:**\n\n'
  u'{answer}\n'
)
TIME_FORMAT = "%b %d, %Y @ %I:%M:%S %P EST"
BASE_URL = u'http://www.reddit.com/'
BOT_NAME = u'narwal_bot'
WAIT_TIME = 60.0

def quotify(s):
  return u'> {}'.format(s.replace('\n', '\n> '))


def get_qa(first_comments, author):
  def helper(comments, parent=None):
    lst = []
    for comment in comments:
      if not isinstance(comment, narwal.things.Comment):
        continue
      if comment.author == author:
        if not parent or parent.author != BOT_NAME:
          lst.append((parent, comment))
      if comment.replies:
        lst += helper(comment.replies, comment)
    return lst
  qalst = helper(first_comments)
  if qalst:
    return sorted(qalst, key=lambda (p, c): c.created)
  else:
    return lst


def format_qa(qalst, host, limit=10000):
  if not qalst:
    return []
  
  rlst = []
  slst = [HEADER_FORMAT.format(last_updated=time.strftime(TIME_FORMAT, time.localtime()),
                               host=host)]
  charcount = 0
  page = 1
  for q, a in qalst:
    if q:
      s = QA_FORMAT.format(qlink=q.permalink,
                           alink=a.permalink,
                           asker=q.author if q.author else u'[deleted]',
                           question=quotify(q.body if q.body else u'[deleted]'),
                           host=host,
                           answer=quotify(a.body))
    else:
      s = TOP_FORMAT.format(answer=quotify(a.body))
    charcount += len(s) + 1
    if charcount >= limit:
      rlst.append('\n'.join(slst))
      page += 1
      header = SECOND_HEADER_FORMAT.format(page) 
      slst = [header,
              s]
      charcount = len(s) + len(header)
    else:
      slst.append(s)
  if slst:
    rlst.append('\n'.join(slst))
  return rlst


def process_iama(db, iama):
  host = iama.author
  comments = iama.comments()
  
  qalst = get_qa(comments, host)
  if not qalst:
    return
  sqalst = format_qa(qalst, host)
  
  query = {'link': iama.permalink}
  old_comp = db.comps.find_one(query)
  old_sqalst = old_comp['sqalst'] if old_comp else None
  
  new_sqalst = []
  rid = iama.name
  for i, sqa in enumerate(sqalst):
    if old_sqalst and i < len(old_sqalst):
      rid = old_sqalst[i]['rid']
      if i == 0 or sqa.split(u'\n', 1)[1] != old_sqalst[i]['body'].split(u'\n', 1)[1]:
        c = iama._reddit.edit(rid, sqa)
        print u'Edited', c.permalink
      else:
        print u'No change:', rid
    else:
      c = iama._reddit.comment(rid, sqa)
      rid = c.name
      print u'Posted', c.permalink
    new_sqalst.append({'rid': rid,
                       'body': sqa})
    print u'Waiting {} seconds...'.format(WAIT_TIME)
    time.sleep(WAIT_TIME)

  new_comp = {'link': iama.permalink,
              'sqalst': new_sqalst}
  
  db.comps.update(query, 
                  {'$set': new_comp},
                  upsert=True)
  print u'Finished:', iama.permalink


def main():
  connection = pymongo.Connection(MONGO_URI)
  db = connection[DB_NAME]
  api = narwal.connect(USERNAME, PASSWORD, user_agent='narwal_bot iama bot')
  if len(sys.argv) == 2:
    path = sys.argv[1]
    if path.startswith(BASE_URL):
      path = path[len(BASE_URL):]
    iama = api.get(path)[0][0]
    process_iama(db, iama)
  else:
    iamas = [iama for iama in api.hot('iama')
             if (iama.num_comments > MIN_COMMENTS and
                 'request' not in iama.title)]
    for iama in iamas:
      process_iama(db, iama)


if __name__ == "__main__":
  print 'Going!'
  main()