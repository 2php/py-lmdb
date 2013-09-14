
lmdb
====

`http://github.com/dw/py-lmdb <http://github.com/dw/py-lmdb>`_

.. currentmodule:: lmdb

.. toctree::
    :hidden:
    :maxdepth: 2

This is a universal Python binding for the `OpenLDAP LMDB 'Lightning' Database
<http://symas.com/mdb/>`_. Two implementations are provided and automatically
selected during installation, depending on host environment: a `cffi
<http://cffi.readthedocs.org/en/release-0.5/>`_ implementation that supports
`PyPy <http://www.pypy.org/>`_ and all versions of CPython >=2.6, and a custom
module that supports CPython 2.5-2.7 and >=3.3. Both implementations provide
the same interface.

LMDB is a tiny database with some excellent properties:

* Ordered-map interface (keys are always sorted)
* Reader/writer transactions: readers don't block writers and writers don't
  block readers. Each environment supports one concurrent write transaction.
* Read transactions are extremely cheap: under 400 nanoseconds on CPython.
* Environments may be opened by multiple processes on the same host, making it
  ideal for working around Python's `GIL
  <http://wiki.python.org/moin/GlobalInterpreterLock>`_.
* Multiple sub-databases may be created with transactions covering all
  sub-databases.
* Memory mapped, allowing for zero copy lookup and iteration. This is
  optionally exposed to Python using the :py:func:`buffer` interface.
* Maintenance requires no external process or background threads.
* No application-level caching is required: LMDB relies entirely on the
  operating system's buffer cache.
* 32kb of object code and 6kLOC of C.


Installation
++++++++++++

For convenience, a supported version of the LMDB library is bundled inline with
the binding and built statically by default. If your system has an install of
LMDB available, set the ``LMDB_FORCE_SYSTEM`` environment variable, and
optionally ``LMDB_INCLUDEDIR`` and ``LMDB_LIBDIR`` prior to invoking
``setup.py``.

*Note:* on PyPy the wrapper depends on cffi which in turn depends on
``libffi``, so you may need to install the development package for it. Both
wrappers additionally depend on the CPython development headers when running
under CPython. On Debian/Ubuntu:

    ::

        apt-get install libffi-dev python-dev build-essential

To install the Python module, ensure a C compiler and `pip` or `easy_install`
are available and type:

    ::

        pip install lmdb
        # or
        easy_install lmdb

You may also use the cffi version on CPython. This is accomplished by setting
the ``LMDB_FORCE_CFFI`` environment variable before installation or before
module import with an existing installation:

    ::

        >>> import os
        >>> os.environ['LMDB_FORCE_CFFI'] = '1'

        >>> # cffi version is loaded.
        >>> import lmdb


Sub-databases
+++++++++++++

To use the sub-database feature you must call :py:func:`lmdb.open` or
:py:class:`lmdb.Environment` with a `max_dbs=` parameter set to the number of
databases required. This must be done by the first process or thread opening
the environment as it is used to allocate resources kept in shared memory.

.. caution::

    LMDB implements sub-databases by *storing a special descriptor key in the
    main database*. All databases in an environment *share the same file*.
    Because a sub-database is just a key in the main database, attempts to
    create one will fail if this key already exists. Furthermore *the key is
    visible to lookups and enumerations*. If your main database keyspace
    conflicts with the names you are using for sub-databases then consider
    moving the contents of your main database to another sub-database.

    ::

        >>> env = lmdb.open('/tmp/test', max_dbs=2)
        >>> with env.begin(write=True) as txn
        ...     txn.put('somename', 'somedata')

        >>> # Error: database cannot share name of existing key!
        >>> subdb = env.open_db('somename')

When a sub-database has been opened with :py:meth:`Environment.open_db` the
resulting handle is shared with all environment users. In particular this means
any user calling :py:meth:`Environment.close_db` will invalidate the handle for
all users. For this reason databases are never closed automatically, you must
do it explicitly.

There is little reason to close a handle: open handles only consume slots in
the shared environment and repeated calls to :py:meth:`Environment.open_db` for
the same name return the same handle. Simply setting `max_dbs=` higher than the
maximum number of handles required will alleviate any need to coordinate
management amongst users.


Storage efficiency & limits
+++++++++++++++++++++++++++

LMDB groups records in pages matching the operating system memory manager's
page size which is usually 4096 bytes. In order to maintain its internal
structure each page must contain a minimum of 2 records, in addition to 8 bytes
per record and a 16 byte header. Due to this the engine is most space-efficient
when the combined size of any (8+key+value) combination does not exceed 2040
bytes.

When an attempt to store a record would exceed the maximum size, its value part
is written separately to one or more pages. Since the trailer of the last page
containing the record value cannot be shared with other records, it is more
efficient when large values are an approximate multiple of 4096 bytes, minus 16
bytes for an initial header.

Space usage can be monitored using :py:meth:`Environment.stat`:

        ::

            >>> pprint(env.stat())
            {'branch_pages': 1040L,
             'depth': 4L,
             'entries': 3761848L,
             'leaf_pages': 73658L,
             'overflow_pages': 0L,
             'psize': 4096L}

This database contains 3,761,848 records and no values were spilled
(``overflow_pages``).

By default record keys are limited to 511 bytes in length, however this can be
adjusted by rebuilding the library.


Buffers
+++++++

Since LMDB is memory mapped it is possible to access record data without keys
or values ever being copied by the kernel, database library, or application. To
exploit this the library can be instructed to return :py:func:`buffer` objects
instead of strings by passing `buffers=True` to :py:meth:`Environment.begin` or
:py:class:`Transaction`.

In Python :py:func:`buffer` objects can be used in many places where strings
are expected. In every way they act like a regular sequence: they support
slicing, indexing, iteration, and taking their length. Many Python APIs will
automatically convert them to bytestrings as necessary, since they also
implement ``__str__()``:

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

It is also possible to pass buffers directly to many native APIs, for example
:py:meth:`file.write`, :py:meth:`socket.send`, :py:meth:`zlib.decompress` and
so on.

A buffer may be sliced without copying by passing it to :py:func:`buffer`:

    ::

        >>> # Extract bytes 10 through 210:
        >>> sub_buf = buffer(buf, 10, 200)
        >>> len(sub_buf)
        200

.. caution::

    In CPython buffers returned by :py:class:`Transaction` and
    :py:class:`Cursor` are reused, so that consecutive calls to
    :py:class:`Transaction.get` or any of the :py:class:`Cursor` methods will
    overwrite the objects that have already been returned. To preserve a value
    returned in a buffer, convert it to a string using :py:func:`str`.

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

    In both PyPy and CPython, returned buffer objects *must be discarded* after
    their generating transaction has completed.


Memsink Protocol
++++++++++++++++

If the ``memsink`` package is available during installation of the CPython
extension, then the resulting module's :py:class:`Transaction` object will act
as a `source` for the `Memsink Protocol
<https://github.com/dw/acid/issues/23>`_. This is an experimental protocol to
allow extension of LMDB's zero-copy design outward to other C types, without
requiring explicit management by the user.

This design is a work in progress; if you have an application that would
benefit from it, please leave a comment on the ticket above.


``writemap`` mode
+++++++++++++++++

When :py:class:`Environment` or :py:func:`open` is invoked with
``writemap=True``, the library will use a writeable memory mapping to directly
update storage. This improves performance at a cost to safety: it is possible
(though fairly unlikely) for buggy C code in the Python process to accidentally
overwrite the map, resulting in database corruption.

.. caution::

    This option may cause filesystems that don't support sparse files, such as
    OSX, to immediately preallocate `map_size=` bytes of underlying storage.


Transaction management
++++++++++++++++++++++

On CPython the :py:class:`Environment` :py:meth:`get <Environment.get>`,
:py:meth:`gets <Environment.gets>`, :py:meth:`put <Environment.put>`,
:py:meth:`puts <Environment.puts>`, :py:meth:`delete <Environment.delete>`,
:py:meth:`deletes <Environment.deletes>`, and :py:meth:`cursor
<Environment.cursor>` methods are implemented so that no temporary
:py:class:`Transaction` is constructed, improving performance in a common case.
Since the begin/do/commit is implemented in C, for simple operations they are
faster than equivalent Python code using :py:class:`Transaction` or
:py:meth:`Environment.begin`, and writes hold an exclusive lock for a shorter
period. Currently CFFI uses a more obvious implementation of these methods.

``MDB_NOTLS`` mode is used exclusively, which allows read transactions to
freely migrate across threads and for a single thread to maintain multiple read
transactions. This enables mostly care-free use of read transactions, for
example when using `gevent <http://www.gevent.org/>`_.

.. caution::

    While any reader exists, writers cannot reuse space in the database file
    that has become unused in later versions. Due to this, continual use of
    long-lived read transactions may cause the database to grow without bound.
    A lost reference to a read transaction will simply be aborted (and its
    reader slot freed) when the :py:class:`Transaction` is eventually garbage
    collected. This should occur immediately on CPython, but may be deferred
    indefinitely on PyPy.

    However the same is *not* true for write transactions: losing a reference
    to a write transaction can lead to deadlock, particularly on PyPy, since if
    the same process that lost the :py:class:`Transaction` reference
    immediately starts another write transaction, it will deadlock on its own
    lock. Subsequently the lost transaction may never be garbage collected
    (since the process is now blocked on itself) and the database will become
    unusable.

These problems are easily avoided by always wrapping :py:class:`Transaction` in
a ``with`` statement somewhere on the stack:

.. code-block:: python

    # Even if this crashes, txn will be correctly finalized.
    with env.begin() as txn:
        if txn.get('foo'):
            function_that_stashes_away_txn_ref(txn)
            function_that_leaks_txn_refs(txn)
            crash()


Interface
+++++++++

.. py:function:: lmdb.open(path, **kwargs)
   
   Shortcut for :py:class:`Environment` constructor.


.. autofunction:: lmdb.version


Environment class
#################

.. autoclass:: lmdb.Environment
    :members:


Transaction class
#################

.. autoclass:: lmdb.Transaction
    :members:


Cursor class
############

.. autoclass:: lmdb.Cursor
    :members:


Exceptions
##########

.. autoclass:: lmdb.Error ()
.. autoclass:: lmdb.KeyExistsError ()
.. autoclass:: lmdb.NotFoundError ()
.. autoclass:: lmdb.PageNotFoundError ()
.. autoclass:: lmdb.CorruptedError ()
.. autoclass:: lmdb.PanicError ()
.. autoclass:: lmdb.VersionMismatchError ()
.. autoclass:: lmdb.InvalidError ()
.. autoclass:: lmdb.MapFullError ()
.. autoclass:: lmdb.DbsFullError ()
.. autoclass:: lmdb.ReadersFullError ()
.. autoclass:: lmdb.TlsFullError ()
.. autoclass:: lmdb.TxnFullError ()
.. autoclass:: lmdb.CursorFullError ()
.. autoclass:: lmdb.PageFullError ()
.. autoclass:: lmdb.MapResizedError ()
.. autoclass:: lmdb.IncompatibleError ()
.. autoclass:: lmdb.BadRslotError ()
.. autoclass:: lmdb.BadTxnError ()
.. autoclass:: lmdb.BadValsizeError ()
.. autoclass:: lmdb.ReadonlyError ()
.. autoclass:: lmdb.InvalidParameterError ()
.. autoclass:: lmdb.LockError ()
.. autoclass:: lmdb.MemoryError ()
.. autoclass:: lmdb.DiskError ()


Threading control
#################

.. autofunction:: lmdb.enable_drop_gil


Command line tools
++++++++++++++++++

A rudimentary interface to most of the binding's functionality is provided.
These functions are useful for e.g. backup jobs.

::

    $ python -mlmdb --help
    Usage: python -mlmdb [options] <command>

    Basic tools for working with LMDB.

        copy: Consistent high speed backup an environment.
            python -mlmdb copy -e source.lmdb target.lmdb

        copyfd: Consistent high speed backup an environment to stdout.
            python -mlmdb copyfd -e source.lmdb > target.lmdb/data.mdb

        drop: Delete one or more sub-databases.
            python -mlmdb drop db1

        dump: Dump one or more databases to disk in 'cdbmake' format.
            Usage: dump [db1=file1.cdbmake db2=file2.cdbmake]

            If no databases are given, dumps the main database to 'main.cdbmake'.

        edit: Add/delete/replace values from a database.
            python -mlmdb edit --set key=value --set-file key=/path \
                       --add key=value --add-file key=/path/to/file \
                       --delete key

        get: Read one or more values from a database.
            python -mlmdb get [<key1> [<keyN> [..]]]

        readers: Display readers in the lock table
            python -mlmdb readers -e /path/to/db [-c]

            If -c is specified, clear stale readers.

        restore: Read one or more database from disk in 'cdbmake' format.
            python -mlmdb restore db1=file1.cdbmake db2=file2.cdbmake

            The special db name ":main:" may be used to indicate the main DB.

        rewrite: Re-create an environment using MDB_APPEND
            python -mlmdb rewrite -e src.lmdb -E dst.lmdb [<db1> [<dbN> ..]]

            If no databases are given, rewrites only the main database.

        shell: Open interactive console with ENV set to the open environment.

        stat: Print environment statistics.

        warm: Read environment into page cache sequentially.

        watch: Show live environment statistics

    Options:
      -h, --help            show this help message and exit
      -e ENV, --env=ENV     Environment file to open
      -d DB, --db=DB        Database to open (default: main)
      -r READ, --read=READ  Open environment read-only
      -S MAP_SIZE, --map_size=MAP_SIZE
                            Map size in megabytes (default: 10)
      -a, --all             Make "dump" dump all databases
      -T TXN_SIZE, --txn_size=TXN_SIZE
                            Writes per transaction (default: 1000)
      -E TARGET_ENV, --target_env=TARGET_ENV
                            Target environment file for "dumpfd"
      -x, --xxd             Print values in xxd format
      -M MAX_DBS, --max-dbs=MAX_DBS
                            Maximum open DBs (default: 128)
      --out-fd=OUT_FD       "copyfd" command target fd

      Options for "edit" command:
        --set=SET           List of key=value pairs to set.
        --set-file=SET_FILE
                            List of key pairs to read from files.
        --add=ADD           List of key=value pairs to add.
        --add-file=ADD_FILE
                            List of key pairs to read from files.
        --delete=DELETE     List of key=value pairs to delete.

      Options for "readers" command:
        -c, --clean         Clean stale readers? (default: no)

      Options for "watch" command:
        --csv               Generate CSV instead of terminal output.
        --interval=INTERVAL Interval size (default: 1sec)
        --window=WINDOW     Average window size (default: 10)
