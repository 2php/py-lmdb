#
# This is not a test suite! More like a collection of triggers for previously
# observed crashes. Want to contribute to py-lmdb? Please write a test suite!
#

import operator
import os
import shutil
import unittest
import random

import lmdb


DB_PATH = '/ram/dbtest'


def make_asserter(op, ops):
    def ass(x, y, msg='', *a):
        if msg:
            if a:
                msg %= a
            msg = ' (%s)' % msg

        f = '%r %s %r%s'
        assert op(x, y), f % (x, ops, y, msg)
    return ass

lt = make_asserter(operator.lt, '<')
eq = make_asserter(operator.eq, '==')
le = make_asserter(operator.le, '<=')

def assertCrash(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except (TypeError, lmdb.Error):
        return
    assert 0, '%r(%r, %r) did not crash as expected' % (fn, args, kwargs)


def rmenv():
    if os.path.exists(DB_PATH):
        shutil.rmtree(DB_PATH)

def openenv(**kwargs):
    return lmdb.open(DB_PATH, max_dbs=10, **kwargs)


class EnvMixin:
    def setUp(self):
        rmenv()
        self.env = openenv(map_size=1048576*1024)

    def tearDown(self):
        self.env.close()
        del self.env
        shutil.rmtree(DB_PATH)


class CrashTest(EnvMixin, unittest.TestCase):
    # Various efforts to cause segfaults.

    def setUp(self):
        EnvMixin.setUp(self)
        with self.env.begin(write=True) as txn:
            txn.put('dave', '')
            txn.put('dave2', '')

    def testOldCrash(self):
        txn = self.env.begin()
        dir(iter(txn.cursor()))

    def testCloseWithTxn(self):
        txn = self.env.begin(write=True)
        self.env.close()
        assertCrash(lambda: list(txn.cursor()))

    def testDoubleClose(self):
        self.env.close()
        self.env.close()

    def testDbDoubleClose(self):
        db = self.env.open_db(name='dave3')
        #db.close()
        #db.close()

    def testTxnCloseActiveIter(self):
        with self.env.begin() as txn:
            it = txn.cursor().iternext()
        assertCrash(lambda: list(it))

    def testDbCloseActiveIter(self):
        db = self.env.open_db(name='dave3')
        with self.env.begin(write=True) as txn:
            txn.put('a', 'b', db=db)
            it = txn.cursor(db=db).iternext()
        assertCrash(lambda: list(it))


class LeakTest(EnvMixin, unittest.TestCase):
    # Various efforts to cause Python-level leaks.
    pass



KEYS = 'a', 'b', 'baa', 'd'
ITEMS = [(k, '') for k in KEYS]
REV_ITEMS = ITEMS[::-1]
VALUES = ['' for k in KEYS]

def putData(t, db=None):
    for k, v in ITEMS:
        if db:
            t.put(k, v, db=db)
        else:
            t.put(k, v)


class CursorTest(EnvMixin, unittest.TestCase):
    def setUp(self):
        EnvMixin.setUp(self)
        self.txn = self.env.begin(write=True)
        self.c = self.txn.cursor()

    def testKeyValueItemEmpty(self):
        eq('', self.c.key())
        eq('', self.c.value())
        eq(('', ''), self.c.item())

    def testFirstLastEmpty(self):
        eq(False, self.c.first())
        eq(False, self.c.last())

    def testFirstFilled(self):
        putData(self.txn)
        eq(True, self.c.first())
        eq(ITEMS[0], self.c.item())

    def testLastFilled(self):
        putData(self.txn)
        eq(True, self.c.last())
        eq(ITEMS[-1], self.c.item())

    def testSetKey(self):
        assertCrash(lambda: self.c.set_key(''))
        eq(False, self.c.set_key('missing'))
        putData(self.txn)
        eq(True, self.c.set_key('b'))
        eq(False, self.c.set_key('ba'))

    def testSetRange(self):
        eq(False, self.c.set_range('x'))
        putData(self.txn)
        eq(False, self.c.set_range('x'))
        eq(True, self.c.set_range('a'))
        eq('a', self.c.key())
        eq(True, self.c.set_range('ba'))
        eq('baa', self.c.key())
        self.c.set_range('')
        eq('a', self.c.key())

    def testDeleteEmpty(self):
        eq(False, self.c.delete())

    def testDeleteFirst(self):
        putData(self.txn)
        eq(False, self.c.delete())
        self.c.first()
        eq(('a', ''), self.c.item())
        eq(True, self.c.delete())
        eq(('b', ''), self.c.item())
        eq(True, self.c.delete())
        eq(('baa', ''), self.c.item())
        eq(True, self.c.delete())
        eq(('d', ''), self.c.item())
        eq(True, self.c.delete())
        eq(('', ''), self.c.item())
        eq(False, self.c.delete())
        eq(('', ''), self.c.item())

    def testDeleteLast(self):
        putData(self.txn)
        eq(True, self.c.last())
        eq(('d', ''), self.c.item())
        eq(True, self.c.delete())
        eq(('', ''), self.c.item())
        eq(False, self.c.delete())
        eq(('', ''), self.c.item())

    def testCount(self):
        assertCrash(lambda: self.c.count())
        putData(self.txn)
        self.c.first()
        # TODO: complete dup key support.
        #eq(1, self.c.count())

    def testPut(self):
        pass

class IteratorTest(EnvMixin, unittest.TestCase):
    def setUp(self):
        EnvMixin.setUp(self)
        self.txn = self.env.begin(write=True)
        self.c = self.txn.cursor()

    def testEmpty(self):
        eq([], list(self.c))
        eq([], list(self.c.iternext()))
        eq([], list(self.c.iterprev()))

    def testFilled(self):
        putData(self.txn)
        eq(ITEMS, list(self.c))
        eq(ITEMS, list(self.c))
        eq(ITEMS, list(self.c.iternext()))
        eq(ITEMS[::-1], list(self.txn.cursor().iterprev()))
        eq(ITEMS[::-1], list(self.c.iterprev()))
        eq(ITEMS, list(self.c))

    def testFilledSkipForward(self):
        putData(self.txn)
        self.c.set_range('b')
        eq(ITEMS[1:], list(self.c))

    def testFilledSkipReverse(self):
        putData(self.txn)
        self.c.set_range('b')
        eq(REV_ITEMS[-2:], list(self.c.iterprev()))

    def testFilledSkipEof(self):
        putData(self.txn)
        eq(False, self.c.set_range('z'))
        eq(REV_ITEMS, list(self.c.iterprev()))



class BigReverseTest(EnvMixin, unittest.TestCase):
    # Test for issue with MDB_LAST+MDB_PREV skipping chunks of database.
    def test_big_reverse(self):
        txn = self.env.begin(write=True)
        keys = ['%05d' % i for i in xrange(0xffff)]
        for k in keys:
            txn.put(k, k, append=True)
        assert list(txn.cursor().iterprev(values=False)) == list(reversed(keys))


class MultiCursorDeleteTest(EnvMixin, unittest.TestCase):
    def test1(self):
        """Ensure MDB_NEXT is ignored on `c1' when it was previously positioned
        on the key that `c2' just deleted."""
        txn = self.env.begin(write=True)
        cur = txn.cursor()
        while cur.first():
            print 'Deleting', cur.key()
            cur.delete()

        for i in xrange(1, 10):
            cur.put(chr(ord('a') + i) * i, '')

        c1 = txn.cursor()
        c1f = c1.iternext(values=False)
        while next(c1f) != 'ddd':
            pass
        c2 = txn.cursor()
        assert c2.set_key('ddd')
        c2.delete()
        assert next(c1f) == 'eeee'


    def test_monster(self):
        # Generate predictable sequence of sizes.
        rand = random.Random()
        rand.seed(0)

        txn = self.env.begin(write=True)
        keys = []
        for i in xrange(20000):
            key = '%06x' % i
            val = 'x' * rand.randint(76, 350)
            assert txn.put(key, val)
            keys.append(key)

        deleted = 0
        for key in txn.cursor().iternext(values=False):
            #print 'got key', key, 'deleting..'
            print repr(key), deleted
            assert txn.delete(key), key
            deleted += 1

        assert deleted == len(keys), deleted



if __name__ == '__main__':
    unittest.main()


# what happens when empty keys/ values passed to various funcs
# incorrect types
# try to break cpython arg parsing - too many/few/incorrect args
