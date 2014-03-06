#
# Copyright 2013 The py-lmdb authors, all rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted only as authorized by the OpenLDAP
# Public License.
#
# A copy of this license is available in the file LICENSE in the
# top-level directory of the distribution or, alternatively, at
# <http://www.OpenLDAP.org/license.html>.
#
# OpenLDAP is a registered trademark of the OpenLDAP Foundation.
#
# Individual files and/or contributed packages may be copyright by
# other parties and/or subject to additional restrictions.
#
# This work also contains materials derived from public sources.
#
# Additional information about OpenLDAP can be obtained at
# <http://www.openldap.org/>.
#

from __future__ import absolute_import
from __future__ import with_statement
import unittest

import testlib
from testlib import B
from testlib import BT
from testlib import OCT
from testlib import INT_TYPES
from testlib import BytesType
from testlib import UnicodeType

import lmdb


class InitTest(unittest.TestCase):
    def test_closed(self):
        _, env = testlib.temp_env()
        env.close()
        self.assertRaises(Exception,
            lambda: lmdb.Transaction(env))

    def test_readonly(self):
        _, env = testlib.temp_env()
        txn = lmdb.Transaction(env)
        # Read txn can't write.
        self.assertRaises(lmdb.ReadonlyError,
            lambda: txn.put(B('a'), B('')))
        txn.abort()

    def test_begin_write(self):
        _, env = testlib.temp_env()
        txn = lmdb.Transaction(env, write=True)
        # Write txn can write.
        assert txn.put(B('a'), B(''))
        txn.commit()

    def test_bind_db(self):
        _, env = testlib.temp_env()
        main = env.open_db(None)
        sub = env.open_db('db1')

        txn = lmdb.Transaction(env, write=True, db=sub)
        assert txn.put(B('b'), B(''))           # -> sub
        assert txn.put(B('a'), B(''), db=main)  # -> main
        txn.commit()

        txn = lmdb.Transaction(env)
        assert txn.get(B('a')) == B('')
        assert txn.get(B('b')) is None
        assert txn.get(B('a'), db=sub) is None
        assert txn.get(B('b'), db=sub) == B('')
        txn.abort()

    def test_bind_db_methods(self):
        _, env = testlib.temp_env()
        maindb = env.open_db(None)
        db1 = env.open_db('d1')
        txn = lmdb.Transaction(env, write=True, db=db1)
        assert txn.put(B('a'), B('d1'))
        assert txn.get(B('a'), db=db1) == B('d1')
        assert txn.get(B('a'), db=maindb) is None
        assert txn.replace(B('a'), B('d11')) == B('d1')
        assert txn.pop(B('a')) == B('d11')
        assert txn.put(B('a'), B('main'), db=maindb, overwrite=False)
        assert not txn.delete(B('a'))
        txn.abort()

    def test_parent_readonly(self):
        _, env = testlib.temp_env()
        parent = lmdb.Transaction(env)
        # Nonsensical.
        self.assertRaises(lmdb.InvalidParameterError,
            lambda: lmdb.Transaction(env, parent=parent))

    def test_parent(self):
        _, env = testlib.temp_env()
        parent = lmdb.Transaction(env, write=True)
        parent.put(B('a'), B('a'))

        child = lmdb.Transaction(env, write=True, parent=parent)
        assert child.get(B('a')) == B('a')
        assert child.put(B('a'), B('b'))
        child.abort()

        # put() should have rolled back
        assert parent.get(B('a')) == B('a')

        child = lmdb.Transaction(env, write=True, parent=parent)
        assert child.put(B('a'), B('b'))
        child.commit()

        # put() should be visible
        assert parent.get(B('a')) == B('b')

    def test_buffers(self):
        _, env = testlib.temp_env()
        txn = lmdb.Transaction(env, write=True, buffers=True)
        assert txn.put(B('a'), B('a'))
        b = txn.get(B('a'))
        assert b is not None
        assert len(b) == 1
        assert not isinstance(b, type(B('')))
        txn.commit()

        txn = lmdb.Transaction(env, buffers=False)
        b = txn.get(B('a'))
        assert b is not None
        assert len(b) == 1
        assert isinstance(b, type(B('')))
        txn.abort()


class StatTest(unittest.TestCase):
    def test_stat(self):
        _, env = testlib.temp_env()
        db1 = env.open_db('db1')
        db2 = env.open_db('db2')

        txn = lmdb.Transaction(env)
        for db in db1, db2:
            stat = txn.stat(db)
            for k in 'psize', 'depth', 'branch_pages', 'overflow_pages',\
                     'entries':
                assert isinstance(stat[k], INT_TYPES), k
                assert stat[k] >= 0
            assert stat['entries'] == 0

        txn = lmdb.Transaction(env, write=True)
        txn.put(B('a'), B('b'), db=db1)
        txn.commit()

        txn = lmdb.Transaction(env)
        stat = txn.stat(db1)
        assert stat['entries'] == 1

        stat = txn.stat(db2)
        assert stat['entries'] == 0

        txn.abort()
        self.assertRaises(Exception,
            lambda: env.stat(db1))
        env.close()
        self.assertRaises(Exception,
            lambda: env.stat(db1))


class DropTest(unittest.TestCase):
    def test_empty(self):
        _, env = testlib.temp_env()
        db1 = env.open_db('db1')
        txn = env.begin(write=True)
        txn.put(B('a'), B('a'), db=db1)
        assert txn.get(B('a'), db=db1) == B('a')
        txn.drop(db1, False)
        assert txn.get(B('a')) is None
        txn.drop(db1, False)  # should succeed.
        assert txn.get(B('a')) is None

    def test_delete(self):
        _, env = testlib.temp_env()
        db1 = env.open_db('db1')
        txn = env.begin(write=True)
        txn.put(B('a'), B('a'), db=db1)
        txn.drop(db1)
        self.assertRaises(lmdb.InvalidParameterError,
            lambda: txn.get(B('a'), db=db1))
        self.assertRaises(lmdb.InvalidParameterError,
            lambda: txn.drop(db1))


class CommitTest(unittest.TestCase):
    def test_bad_txn(self):
        _, env = testlib.temp_env()
        txn = env.begin()
        txn.abort()
        self.assertRaises(Exception,
            lambda: txn.commit())

    def test_bad_env(self):
        _, env = testlib.temp_env()
        txn = env.begin()
        env.close()
        self.assertRaises(Exception,
            lambda: txn.commit())

    def test_commit_ro(self):
        _, env = testlib.temp_env()
        txn = env.begin()
        txn.commit()
        self.assertRaises(Exception,
            lambda: txn.commit())

    def test_commit_rw(self):
        _, env = testlib.temp_env()
        txn = env.begin(write=True)
        assert txn.put(B('a'), B('a'))
        txn.commit()
        self.assertRaises(Exception,
            lambda: txn.commit())
        txn = env.begin()
        assert txn.get(B('a')) == B('a')
        txn.abort()


class AbortTest(unittest.TestCase):
    def test_abort_ro(self):
        _, env = testlib.temp_env()
        txn = env.begin()
        assert txn.get(B('a')) is None
        txn.abort()
        self.assertRaises(Exception,
            lambda: txn.get(B('a')))
        env.close()
        self.assertRaises(Exception,
            lambda: txn.get(B('a')))

    def test_abort_rw(self):
        _, env = testlib.temp_env()
        txn = env.begin(write=True)
        assert txn.put(B('a'), B('a'))
        txn.abort()
        txn = env.begin()
        assert txn.get(B('a')) is None


class GetTest(unittest.TestCase):
    def test_bad_txn(self):
        _, env = testlib.temp_env()
        txn = env.begin()
        txn.abort()
        self.assertRaises(Exception,
            lambda: txn.get(B('a')))

    def test_bad_env(self):
        _, env = testlib.temp_env()
        txn = env.begin()
        env.close()
        self.assertRaises(Exception,
            lambda: txn.get(B('a')))

    def test_missing(self):
        _, env = testlib.temp_env()
        txn = env.begin()
        assert txn.get(B('a')) is None
        assert txn.get(B('a'), default='default') is 'default'

    def test_empty_key(self):
        _, env = testlib.temp_env()
        txn = env.begin()
        self.assertRaises(lmdb.BadValsizeError,
            lambda: txn.get(B('')))

    def test_db(self):
        _, env = testlib.temp_env()
        maindb = env.open_db(None)
        db1 = env.open_db('db1')

        txn = env.begin()
        assert txn.get(B('a'), db=db1) is None
        txn.abort()

        txn = env.begin(write=True)
        txn.put(B('a'), B('a'), db=db1)
        txn.commit()

        txn = env.begin()
        assert txn.get(B('a')) is None
        txn.abort()

        txn = env.begin(db=db1)
        assert txn.get(B('a')) == B('a')
        assert txn.get(B('a'), db=maindb) is None

    def test_buffers_no(self):
        _, env = testlib.temp_env()
        txn = env.begin(write=True)
        assert txn.put(B('a'), B('a'))
        assert type(txn.get(B('a'))) is BytesType

    def test_buffers_yes(self):
        _, env = testlib.temp_env()
        txn = env.begin(write=True, buffers=True)
        assert txn.put(B('a'), B('a'))
        assert type(txn.get(B('a'))) is not BytesType

    def test_dupsort(self):
        _, env = testlib.temp_env()
        db1 = env.open_db('db1', dupsort=True)
        txn = env.begin(write=True, db=db1)
        assert txn.put(B('a'), B('a'))
        assert txn.put(B('a'), B('b'))
        assert txn.get(B('a')) == B('a')


class PutTest(unittest.TestCase):
    def test_bad_txn(self):
        _, env = testlib.temp_env()
        txn = env.begin(write=True)
        txn.abort()
        self.assertRaises(Exception,
            lambda: txn.put(B('a'), B('a')))

    def test_bad_env(self):
        _, env = testlib.temp_env()
        txn = env.begin(write=True)
        env.close()
        self.assertRaises(Exception,
            lambda: txn.put(B('a'), B('a')))

    def test_ro_txn(self):
        _, env = testlib.temp_env()
        txn = env.begin()
        self.assertRaises(lmdb.ReadonlyError,
            lambda: txn.put(B('a'), B('a')))

    def test_empty_key_value(self):
        _, env = testlib.temp_env()
        txn = env.begin(write=True)
        self.assertRaises(lmdb.BadValsizeError,
            lambda: txn.put(B(''), B('a')))

    def test_dupsort(self):
        _, env = testlib.temp_env()

    def test_dupdata_no_dupsort(self):
        _, env = testlib.temp_env()
        txn = env.begin(write=True)
        assert txn.put(B('a'), B('a'), dupdata=True)
        assert txn.put(B('a'), B('b'), dupdata=True)
        txn.get(B('a'))


if __name__ == '__main__':
    unittest.main()
