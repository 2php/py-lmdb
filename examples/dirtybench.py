
from pprint import pprint
import os
import shutil

from time import time as now
import random
import lmdb

big = '' # '*' * 400

dbpath = '/ram/testdb'
if os.path.exists(dbpath):
    shutil.rmtree(dbpath)

t0 = now()
words = set(file('/usr/share/dict/words').readlines())
words.update([w.upper() for w in words])
words.update([w[::-1] for w in words])
#words.update([w[::-1].upper() for w in words])
#words.update(['-'.join(w) for w in words])
#words.update(['+'.join(w) for w in words])
#words.update(['/'.join(w) for w in words])
words = list(words)
alllen = sum(len(w) for w in words)
avglen = alllen  / len(words)
print 'permutate %d words avglen %d took %.2fsec' % (len(words), avglen, now()-t0)

getword = iter(words).next

env = lmdb.connect(dbpath, map_size=1048576 * 1024)
print 'stat:', env.stat()

run = True
t0 = now()
last = t0
while run:
    with env.begin() as txn:
        try:
            for _ in xrange(50000):
                word = getword()
                txn.put(word, big or word)
        except StopIteration:
            run = False

    t1 = now()
    if (t1 - last) > 2:
        print '%.2fs (%d/sec)' % (t1-t0, len(words)/(t1-t0))
        last = t1

t1 = now()
print 'done all %d in %.2fs (%d/sec)' % (len(words), t1-t0, len(words)/(t1-t0))
last = t1

st = env.stat()
print 'stat:', st
print 'k+v size %.2fkb avg %d, on-disk size: %.2fkb avg %d' %\
    ((2*alllen) / 1024., (2*alllen)/len(words),
     (st['psize'] * st['leaf_pages']) / 1024.,
     (st['psize'] * st['leaf_pages']) / len(words))


with env.begin() as txn:
    t0 = now()
    lst = sum(1 for _ in txn.cursor().forward())
    t1 = now()
    print 'enum %d (key, value) pairs took %.2f sec' % ((lst), t1-t0)

with env.begin() as txn:
    t0 = now()
    for word in words:
        txn.get(word)
    t1 = now()
    print 'rand lookup+verify all keys %.2f sec (%d/sec)' % (t1-t0, lst/(t1-t0))

with env.begin(buffers=True) as txn:
    t0 = now()
    for word in words:
        txn.get(word)
    t1 = now()
    print 'rand lookup all buffers %.2f sec (%d/sec)' % (t1-t0, lst/(t1-t0))

with env.begin(buffers=True) as txn:
    t0 = now()
    lst = sum(1 for _ in txn.cursor().forward())
    t1 = now()
    print 'enum %d (key, value) buffers took %.2f sec' % ((lst), t1-t0)

