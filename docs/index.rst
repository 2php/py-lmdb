
lmdb
====

`http://github.com/dw/py-lmdb <http://github.com/dw/py-lmdb>`_

.. raw:: html

    <div style="border: 2px solid red; background: #ffefef; color: black;
                padding: 1ex; text-align: center; width: 66%; margin: auto;
                font-size: larger">
        <strong style="color: #7f0000">WORK IN PROGRESS</strong><br>
        <br>
        This wrapper is not yet thoroughly documented or heavily tested, but it
        already works well.
    </div>

.. currentmodule:: lmdb

.. toctree::
    :hidden:
    :maxdepth: 2

This is a Python wrapper for the `OpenLDAP MDB 'Lightning Database'
<http://symas.com/mdb/>`_. Two versions are provided, and automatically
selected during installation: a `cffi
<http://cffi.readthedocs.org/en/release-0.5/>`_ version that supports `PyPy
<http://www.pypy.org/>`_, and a custom module for CPython. Python 3.x is not
supported yet.

As no packages are available, the MDB library is currently bundled inline with
the wrapper and built statically.


Introduction
++++++++++++

    MDB is a tiny database with some excellent properties:

    * Ordered-map interface (keys are always sorted)
    * Reader/writer transactions: readers don't block writers and writers don't
      block readers. Each environment supports one concurrent write transaction.
    * Read transactions are extremely cheap: under 400 nanoseconds on CPython.
    * The database may be opened by multiple processes on the same host, making
      it ideal for working around Python's GIL.
    * Multiple sub-databases may be created, with transactions covering all
      sub-databases.
    * Completely memory mapped, allowing for zero copy lookup and iteration.
      This is optionally directly exposed to Python using the :py:func:`buffer`
      interface.
    * Maintenance requires no external process or background threads.
    * No application-level caching is required: MDB relies entirely on the
      operating system's buffer cache.
    * Merely 32kb of object code and 6kLOC of C.


Installation
++++++++++++

    To install the Python module, ensure a C compiler and `pip` or
    `easy_install` are available, and type:

    ::

        pip install lmdb
        # or
        easy_install lmdb

    *Note:* on PyPy, the wrapper depends on cffi, which in turn depends on
    ``libffi``, so you may need to install the development package for it. On
    Debian/Ubuntu:

    ::

        apt-get install libffi-dev

    You may also use the cffi version on CPython. This is accomplished by
    setting the ``LMDB_FORCE_CFFI`` environment variable before installation or
    module import:

    ::

        >>> import os
        >>> os.environ['LMDB_FORCE_CFFI'] = '1'

        >>> # cffi version is loaded.
        >>> import lmdb


Sub-databases
+++++++++++++

    To use the sub-database feature, you must call :py:func:`lmdb.connect` or
    :py:class:`lmdb.Environment` with a `max_dbs=` parameter set to the number
    of sub-databases required. This must be done by the first process or thread
    opening the environment, as it is used to allocate resources kept in shared
    memory.

    **Caution:** MDB implements sub-databases by *storing a special descriptor
    key in the main database*. All databases in an environment *share the same
    file*. Because a sub-database is just a key in the main database, attempts
    to create a sub-database will fail if this key already exists. Furthermore,
    *the key is visible to lookups and enumerations*. If your main database
    keyspace conflicts with the names you are using for sub-databases, then
    consider moving the contents of your main database to another sub-database.

    ::

        >>> env = lmdb.connect('/tmp/test', max_dbs=2)
        >>> with env.begin(write=True) as txn:
        ...     txn.put('somename', 'somedata')

        >>> # Error: database cannot share name of existing key!
        >>> subdb = env.open('somename')


Storage efficiency & limits
+++++++++++++++++++++++++++

    MDB groups records in pages matching the operating system memory manager's
    page size, which is usually 4096 bytes. In order to maintain its internal
    structure, each page must contain a minimum of 2 records, in addition to 8
    bytes per record, and a 116 byte header. Due to this, the engine is most
    space-efficient when the combined size of any (8+key+value) combination
    does not exceed 2040 bytes.

    When an attempt to store a record would exceed the containing page's free
    space, the record's value part is written separately to one or more pages
    of its own. Since the trailer of the last page containing the record value
    cannot be shared with other records, it is more efficient when large record
    values are an approximate multiple of 4080 bytes (4096 - 16 byte header).

    Space usage can be monitored using :py:meth:`Environment.stat`:

        ::

            >>> pprint(env.stat())
            {'branch_pages': 1040L,
             'depth': 4L,
             'entries': 3761848L,
             'leaf_pages': 73658L,
             'overflow_pages': 0L,
             'psize': 4096L}

    This database contains 3,761,848 million records, and none of the records
    had their value spilled to a separate page (``overflow_pages``).

    By default, record keys are limited to 511 bytes in length, however this
    can be adjusted by rebuilding the library.


Buffers
+++++++

    Since MDB is exclusively memory mapped, it is possible to access record
    data without ever copying keys or values. To exploit this, the library can
    be instructed to return :py:func:`buffer` objects instead of strings by
    passing `buffers=True` to :py:meth:`Environment.begin` or
    :py:class:`Transaction`.

    In Python, :py:func:`buffer` objects can be used in many places where
    strings are expected. In every way they act like a regular sequence: they
    support slicing, indexing, iteration, and taking their length. Many Python
    APIs will automatically convert them to bytestrings as necessary, since
    they also implement ``__str__()``:

    ::

        >>> txn = env.begin(buffers=True)
        >>> buf = txn.get('somekey')
        >>> buf
        <read-only buffer ptr 0x12e266010, size 4096 at 0x10d93b970>

        >>> len(buf)
        4096
        >>> buf[0]
        'a'
        >>> buf[:2]
        'ab'
        >>> value = str(buf)
        >>> len(value)
        4096
        >>> type(value)
        <type 'str'>

    It is also possible to pass buffers directly to many native APIs, for
    example :py:meth:`file.write`, :py:meth:`socket.send`,
    :py:meth:`zlib.decompress` and so on.

    A buffer may be sliced without copying by passing it to :py:func:`buffer`:

    ::

        >>> # Extract bytes 10 through 210:
        >>> sub_buf = buffer(buf, 10, 200)
        >>> len(sub_buf)
        200


    **Caution:** in CPython, buffers returned by :py:class:`Transaction` and
    :py:class:`Cursor` are reused, so that consecutive calls to
    :py:class:`Transaction.get` or any of the :py:class:`Cursor` methods will
    overwrite the objects that have already been returned. To keep hold of a
    value returned in a buffer, convert it to a string using :py:func:`str`.

    ::

        >>> txn = env.begin(write=True, buffers=True)
        >>> txn.put('key1', 'value1')
        >>> txn.put('key2', 'value2')

        >>> val1 = txn.get('key1')
        >>> vals1 = str(val1)
        >>> vals1
        'value1'
        >>> val2 = txn.get('key2')
        >>> str(val2)
        'value2'

        >>> # Caution: the buffer object is reused!
        >>> str(val1)
        'value2'

        >>> # But our string copy was preserved!
        >>> vals1
        'value1'

    **Caution:** in both PyPy and CPython, *returned buffers absolutely should
    not be used after their generating transaction has completed, or after you
    modified the database in the same transaction!*



Interface
+++++++++

It is recommended that you also refer to the
`excellent Doxygen comments in the MDB source code <http://www.openldap.org/devel/gitweb.cgi?p=openldap.git;a=blob;f=libraries/liblmdb/lmdb.h>`_,
particularly with regard to thread safety.

.. autofunction:: lmdb.connect


Environment class
#################

.. autoclass:: lmdb.Environment
    :members:


Transaction class
#################

.. autoclass:: lmdb.Transaction
    :members:


Database class
##############

**Note:** unless working with sub-databases, you never need to explicitly
handle the :py:class:`Database` class, as all :py:class:`Transaction` methods
default to the main database.

.. autoclass:: lmdb.Database
    :members:


Cursor class
############

.. autoclass:: lmdb.Cursor
    :members:


Exceptions
##########

.. autoclass:: lmdb.Error
