import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, time, date

from dateutil import parser


########################################################################
## Python DB API Globals
########################################################################
apilevel = " 2.0 "
threadsafety = 0  # no idea, so better safe. I can run queries in multiple threads, but that's not the same thing.
paramstyle = "pyformat"

########################################################################
## Python 3 compatibility
## These types will never show up under python 3, but if I don't declare
## them I'll get a name error when I try to check for them, as I must for
## python 2 compatibility.
########################################################################



########################################################################
## FFI Initilization
########################################################################
from ._p4d_cffi import ffi, lib as lib4d_sql

########################################################################


########################################################################
## Error Classes
########################################################################
class Warning(Exception):
    pass

class Error(Exception):
    pass

class InterfaceError(Error):
    pass

class DatabaseError(Error):
    pass

class DataError(DatabaseError):
    pass

class OperationalError(DatabaseError):
    pass

class IntegrityError(DatabaseError):
    pass

class InternalError(DatabaseError):
    pass

class ProgrammingError(DatabaseError):
    pass

class NotSupportedError(DatabaseError):
    pass
########################################################################

########################################################################
## Data type classes
########################################################################
def DateFromTicks(ticks):
    return Date(*time.localtime(ticks)[:3])

def TimeFromTicks(ticks):
    return Time(*time.localtime(ticks)[3:6])

def TimestampFromTicks(ticks):
    return Timestamp(*time.localtime(ticks)[:6])

########################################################################
class Binary(bytes):
    """"""
    pass


########################################################################
## Cursor Object
########################################################################
class py4d_cursor(object):
    """"""
    arraysize = 1
    pagesize = 100

    __resulttype = None
    __prepared = False
    __closed = False

    @property
    def rownumber(self):
        return self.__rownumber

    @property
    def description(self):
        return self.__description

    @property
    def rowcount(self):
        """"""
        return self.__rowcount

    #----------------------------------------------------------------------
    def setinputsizes(self, sizes):
        """"""
        pass

    #----------------------------------------------------------------------
    def setoutputsize(self, size, column=None):
        """"""
        pass

    #----------------------------------------------------------------------
    def __init__(self, connection, fourdconn, lib4d):
        """Constructor"""
        self.__rowcount = -1
        self.__description = None
        self.__rownumber = None
        self.result = None
        self.fourd_query = None

        self.fourdconn = fourdconn
        self.connection = connection
        self.lib4d_sql = lib4d

    #----------------------------------------------------------------------
    def close(self):
        """Close the database connection"""
        if self.result is not None:
            self.lib4d_sql.fourd_free_result(self.result)
            self.result = None
        self.__description = None
        self.__rowcount = -1
        self.__resulttype = None
        self.__closed = True

    #----------------------------------------------------------------------
    def replace_nth(self, source, search, replace, n):
        """Find the Nth occurance of a string, and replace it with another."""
        i = -1
        for _ in range(n):
            i = source.find(search, i+len(search))
            if i == -1:
                return source  #return an unmodified string if there are not n occurances of value

        isinstance(source, str)
        result = "{}{}{}".format(source[:i],replace,source[i+len(search):])
        return result




    #----------------------------------------------------------------------
    def execute(self, query, params=None, describe=True, pagesize=None):
        """Prepare and execute a database operation"""
        if params is None:
            params = []
        if not self.connection.connected:
            raise InternalError("Database not connected")

        if self.__closed:
            raise InterfaceError("cursor already closed.")

        # See if we are using named parameters. If so, break them out (we always need qmark style in the end)
        if isinstance(params, dict):
            new_params = []
            # Parse query string for references to dict entries
            regex = re.compile(r'%\(([^)]+)\)s')
            for key in re.findall(regex, query):
                new_params.append(params[key])  # Will raise key error if the query string argument is not in params.

            if not new_params:
                # We didn't match anything in the query string for the %()s format markers. Try named (:name) instead
                regex = re.compile(':([A-Za-z0-9]+)')
                for key in re.findall(regex, query):
                    new_params.append(params[key])

            query = re.sub(regex, '?', query)
            params = new_params

        # If using "format" parameter markers, just convert all %<whatever> markers to ?'s
        query = re.sub('%[A-Za-z]', '?', query)
        query = query.replace('%%', '%')  # Unescape escaped percent signs


        # if any parameter is a tuple, we need to modify the query string and
        # make multiple passes through the parameters, breaking out one tuple/list
        # each time.
        while True:
            foundtuple = False
            for idx, param in enumerate(params):
                if isinstance(param, (list, tuple)):
                    foundtuple = True
                    paramlen = len(param)
                    query = self.replace_nth(query, "?",
                                             "({})".format(",".join("?"*paramlen)),
                                             idx+1)  #need 1 based count

                    params = tuple(params[:idx]) + tuple(param) + tuple(params[idx+1:])
                    break  #only handle one tuple at a time, otherwise the idx parameter is off.

            if not foundtuple:
                break

        # Start a new transaction if we are not already in one
        if not self.connection.in_transaction:
            self.connection.__start_transaction__()

        if not self.__prepared:  # Should always be false, unless we are running an executemany
            # Clean up anything from a previous query.
            if self.result is not None and self.result != ffi.NULL:
                self.lib4d_sql.fourd_close_statement(self.result)
                self.result = None

            # Free the previous statement if one exists.
            if self.fourd_query is not None and self.fourd_query != ffi.NULL:
                self.lib4d_sql.fourd_free_statement(self.fourd_query)
                self.fourd_query = None

            self.fourd_query = self.lib4d_sql.fourd_prepare_statement(self.fourdconn, query.encode('utf-8'))

        if self.fourd_query == ffi.NULL:
            error = ffi.string(self.lib4d_sql.fourd_error(self.fourdconn))
            raise ProgrammingError(error)

        # Some data types need special handling, but most we can just convert to a string.
        # All strings need UTF-16LE encoding.
        fourdtypes = defaultdict(lambda: self.lib4d_sql.VK_STRING,
                                 {str: self.lib4d_sql.VK_STRING,
                                  bool: self.lib4d_sql.VK_BOOLEAN,
                                  int: self.lib4d_sql.VK_LONG,
                                  float: self.lib4d_sql.VK_REAL,
                                  })

        for idx, parameter in enumerate(params):
            param_type = type(parameter)
            fourd_type = fourdtypes[param_type]
            manual_clear = False

            if param_type == str:
                # Very similar to the default, but we don't have to call string on the parameter
                param = self.lib4d_sql.fourd_create_string(parameter.encode('UTF-16LE'),
                                                           len(parameter))
                manual_clear = True
            elif param_type == bool:
                param = ffi.new("FOURD_BOOLEAN *", parameter)
            elif param_type == int:
                param = ffi.new("FOURD_LONG *", parameter)
            elif param_type == float:
                param = ffi.new("FOURD_REAL *", parameter)
            elif param_type == None:
                param = ffi.NULL
            elif param_type == time:
                #almost the same as calling str(), but without milliseconds
                itemstr = parameter.strftime('%H:%M:%S')
                param = self.lib4d_sql.fourd_create_string(itemstr.encode('UTF-16LE'),
                                                           len(itemstr))
                manual_clear = True

            elif param_type == tuple:
                numparams = len(parameter)

                itemstr =  str(parameter)
                param = self.lib4d_sql.fourd_create_string(itemstr.encode('UTF-16LE'),
                                                           len(itemstr))
                manual_clear = True

            else:
                itemstr =  str(parameter)
                param = self.lib4d_sql.fourd_create_string(itemstr.encode('UTF-16LE'),
                                                           len(itemstr))
                manual_clear = True


            bound = self.lib4d_sql.fourd_bind_param(self.fourd_query, idx, fourd_type, param)
            if bound != 0:
                raise ProgrammingError(ffi.string(self.lib4d_sql.fourd_error(self.fourdconn)))

            # Clean up any string parameters created by the above calls to fourd_create_string
            if manual_clear:
                self.lib4d_sql.Free(param.data)
                self.lib4d_sql.Free(param)

        # Properly clean up any old results.
        if self.result is not None and self.result != ffi.NULL:
            self.lib4d_sql.fourd_free_result(self.result)
            self.result = None

        # Run the query and return the results
        _pagesize = pagesize if pagesize is not None else self.pagesize
        self.result = self.lib4d_sql.fourd_exec_statement(self.fourd_query, _pagesize)

        if self.result == ffi.NULL:
            raise ProgrammingError(ffi.string(self.lib4d_sql.fourd_error(self.fourdconn)))

        self.__resulttype = self.result.resultType
        if self.__resulttype == self.lib4d_sql.RESULT_SET:
            self.__rowcount = self.lib4d_sql.fourd_num_rows(self.result)
        elif self.__resulttype == self.lib4d_sql.UPDATE_COUNT:
            self.__rowcount = self.lib4d_sql.fourd_affected_rows(self.fourdconn);
        else:
            self.__rowcount = -1  # __resulttype is an enum, so this shouldn't happen.

        self.__rownumber = -1  #not on a row yet

        if describe:
            # Populate the description object
            self.__describe()

    #----------------------------------------------------------------------
    def __describe(self):
        """Populate the description object"""
        if self.result == ffi.NULL:
            return

        columncount = self.lib4d_sql.fourd_num_columns(self.result)

        description = []
        pythonTypes = {self.lib4d_sql.VK_UNKNOW: str,
                       self.lib4d_sql.VK_BOOLEAN: bool,
                       self.lib4d_sql.VK_BYTE: str,
                       self.lib4d_sql.VK_WORD: str,
                       self.lib4d_sql.VK_LONG: int,
                       self.lib4d_sql.VK_LONG8: int,
                       self.lib4d_sql.VK_REAL: float,
                       self.lib4d_sql.VK_FLOAT: float,
                       self.lib4d_sql.VK_TIME: time,
                       self.lib4d_sql.VK_TIMESTAMP: datetime,
                       self.lib4d_sql.VK_DURATION: timedelta,
                       self.lib4d_sql.VK_TEXT: str,
                       self.lib4d_sql.VK_STRING: str,
                       self.lib4d_sql.VK_BLOB: Binary,
                       self.lib4d_sql.VK_IMAGE: Binary,}

        for colidx in range(columncount):
            colName = ffi.string(self.lib4d_sql.fourd_get_column_name(self.result, colidx))
            colType = self.lib4d_sql.fourd_get_column_type(self.result, colidx)
            try:
                pytype = pythonTypes[colType]
            except KeyError:
                raise OperationalError("Unrecognized 4D type: {}".format(str(colType)))

            colDescript = (colName, pytype, None, None, None, None, None)
            description.append(colDescript)

        self.__description = description

    #----------------------------------------------------------------------
    def executemany(self, query, params):
        """"""
        for paramlist in params:
            self.execute(query, paramlist, describe=False)
            # Close and free the last result, then reset prepared flag
            # so the next iteration prepares a fresh statement.
            if self.result is not None and self.result != ffi.NULL:
                self.lib4d_sql.fourd_close_statement(self.result)
                self.lib4d_sql.fourd_free_result(self.result)
                self.result = None
            self.__prepared = False

        # We don't run describe on the individual queries in order to be more efficient.
        self.__describe()

    #----------------------------------------------------------------------
    def fetchone(self):
        """"""
        if self.__closed:
            raise InterfaceError("cursor already closed.")

        if not self.connection.connected:
            raise InternalError("Database not connected")

        if self.__resulttype is None:
            raise DataError("No rows to fetch")

        if self.rowcount == 0 or self.__resulttype == self.lib4d_sql.UPDATE_COUNT:
            return None

        # get the next row of the result set
        #if self.rownumber >= self.result.row_count_sent - 1:
        #    return None  #no more results have been returned

        goodrow = self.lib4d_sql.fourd_next_row(self.result)
        if goodrow == 0:
            return None

        self.__rownumber = self.result.numRow

        numcols = self.lib4d_sql.fourd_num_columns(self.result)
        strlen = ffi.new("size_t*")
        inbuff = ffi.new("char*[1]")

        row=[]
        for col in range(numcols):
            fieldtype=self.lib4d_sql.fourd_get_column_type(self.result,col)
            if self.lib4d_sql.fourd_field(self.result,col)==ffi.NULL:
                        row.append(None)
                        continue

            convert_res = self.lib4d_sql.fourd_field_to_string(self.result, col, inbuff, strlen)
            strdata = inbuff[0]
            if convert_res == 1 and strdata != ffi.NULL:
                output = ffi.buffer(strdata, strlen[0])[:]
                self.lib4d_sql.Free(strdata)
                strdata = ffi.NULL
            else:
                output = b''

            if fieldtype==self.lib4d_sql.VK_STRING or fieldtype==self.lib4d_sql.VK_TEXT:
                decoded_value = output.decode('UTF-16LE', errors="replace")
                row.append(decoded_value)
            elif fieldtype == self.lib4d_sql.VK_BOOLEAN:
                boolval = self.lib4d_sql.fourd_field_long(self.result, col)
                row.append(bool(boolval[0]))
            #numerical types
            elif fieldtype == self.lib4d_sql.VK_LONG or \
                 fieldtype == self.lib4d_sql.VK_LONG8 or \
                 fieldtype == self.lib4d_sql.VK_WORD:
                intval = self.lib4d_sql.fourd_field_long(self.result, col)
                row.append(intval[0])
            elif fieldtype == self.lib4d_sql.VK_REAL or fieldtype == self.lib4d_sql.VK_FLOAT:
                if output == b'':
                    row.append(None)  # Empty output = null
                else:
                    row.append(float(output))
            elif fieldtype == self.lib4d_sql.VK_TIMESTAMP:
                try:
                    s = output.decode('ascii')
                    if s == '0000/00/00 00:00:00.000':
                        dateval = None
                    else:
                        dateval = datetime(int(s[:4]), int(s[5:7]),
                                           int(s[8:10]), int(s[11:13]),
                                           int(s[14:16]), int(s[17:19]),
                                           int(s[20:23])*1000)
                except Exception:
                    dateval = None
                row.append(dateval)
            elif fieldtype == self.lib4d_sql.VK_DURATION:
                longval = self.lib4d_sql.fourd_field_long(self.result, col)
                try:
                    durationval = timedelta(milliseconds=longval[0])
                    midnight = datetime(1, 1, 1)
                    timeval = midnight + durationval
                    row.append(timeval.time())
                except (OverflowError, ValueError):
                    row.append(None)
            elif fieldtype == self.lib4d_sql.VK_BLOB or fieldtype == self.lib4d_sql.VK_IMAGE:
                field = self.lib4d_sql.fourd_field(self.result, col)
                if field != ffi.NULL:
                    # Use cast to let the system know this is a BLOB type field
                    field = ffi.cast("FOURD_BLOB *", field)
                    fieldlen = field.length
                    fielddata = ffi.buffer(field.data, fieldlen)[:]
                    blobbuff = Binary(fielddata)
                    row.append(blobbuff)
                else:
                    row.append(None)
            else:
                row.append(output)

        return tuple(row)

    #----------------------------------------------------------------------
    def fetchmany(self, size=arraysize):
        """"""
        if not self.connection.connected:
            raise InternalError("Database not connected")

        if self.__closed:
            raise InterfaceError("cursor already closed.")

        if self.__resulttype is None:
            raise DataError("No rows to fetch")

        resultset = []
        for i in range(size):
            row = self.fetchone()
            if row is None:
                break
            resultset.append(row)

        return resultset

    #----------------------------------------------------------------------
    def fetchall(self):
        """"""
        if not self.connection.connected:
            raise InternalError("Database not connected")

        if self.__closed:
            raise InterfaceError("cursor already closed.")

        if self.__resulttype is None:
            raise DataError("No rows to fetch")

        resultset = []
        while True:
            row = self.fetchone()
            if row is None:
                break
            resultset.append(row)

        return resultset

    #----------------------------------------------------------------------
    def __next__(self):
        """Return the next result row"""
        result = self.fetchone()
        if result is None:
            raise StopIteration
        return result

    #----------------------------------------------------------------------
    def __iter__(self):
        """"""
        return self

    #----------------------------------------------------------------------
    def __del__(self):
        """Garbage collector"""
        if self.fourd_query is not None and self.fourd_query != ffi.NULL:
            self.lib4d_sql.fourd_free_statement(self.fourd_query)

    #----------------------------------------------------------------------
    def __enter__(self):
        """"""
        return self

    #----------------------------------------------------------------------
    def __exit__(self, ex_type, ex_val, tb):
        """"""
        if self.fourd_query is not None and self.fourd_query != ffi.NULL:
            self.lib4d_sql.fourd_free_statement(self.fourd_query)
            self.fourd_query = None



########################################################################
## Connection object
########################################################################
class py4d_connection:
    """Connection object for a 4D database"""

    in_transaction = False

    #----------------------------------------------------------------------
    def __init__(self, host, user, password, database, port):
        """Initalize a connection object and connect to a server"""
        self.connptr = lib4d_sql.fourd_init()
        self.cursors = []
        if self.connptr == ffi.NULL:
            raise InterfaceError("Unable to intialize connection object")

        connected = lib4d_sql.fourd_connect(self.connptr,
                                            host.encode('utf-8'),
                                            user.encode('utf-8'),
                                            password.encode('utf-8'),
                                            database.encode('utf-8'),
                                            port)
        if connected != 0:
            self.connected = False
            raise OperationalError("Unable to connect to 4D Server: {}".format(ffi.string(self.connptr.error_string)))
        else:
            self.connected = True
            self.__private_cursor__ = self.cursor()

    #----------------------------------------------------------------------
    def __start_transaction__(self):
        """"""
        if self.in_transaction:
            return  # already in transaction, don't do anything
        self.in_transaction = True
        self.__private_cursor__.execute("START TRANSACTION")

    #----------------------------------------------------------------------
    def close(self):
        """Close the connection to the 4D database"""
        # Implicit rollback of any transactions
        if self.in_transaction:
            self.__private_cursor__.execute("ROLLBACK")

        if self.cursors:
            for cursor in self.cursors:
                if cursor.result is not None and cursor.result != ffi.NULL:
                    lib4d_sql.fourd_free_result(cursor.result)
                    cursor.result = None

        if self.connected:
            disconnect = lib4d_sql.fourd_close(self.connptr)
            if disconnect != 0:
                self.connected = False
                print("Disconnect returned code: {}".format(disconnect))
                raise OperationalError("Failed to close connection to 4D Server")
            lib4d_sql.fourd_free(self.connptr)

        self.connected = False

    #----------------------------------------------------------------------
    def commit(self):
        """Commit the current transaction, and set the flag"""
        if self.in_transaction:
            self.__private_cursor__.execute("COMMIT")
        self.in_transaction = False

    #----------------------------------------------------------------------
    def rollback(self):
        """ROLLBACK the current transaction, and start a new one"""
        if self.in_transaction:
            self.__private_cursor__.execute("ROLLBACK")
        self.in_transaction = False

    #----------------------------------------------------------------------
    def cursor(self):
        cursor = py4d_cursor(self, self.connptr, lib4d_sql)
        self.cursors.append(cursor)
        return cursor

    #----------------------------------------------------------------------
    def __enter__(self):
        """"""
        return self

    #----------------------------------------------------------------------
    def __exit__(self, ex_type, ex_val, tb):
        """"""
        if ex_type is not None:
            if self.in_transaction:
                self.rollback()
                return False  # Procede to normal handling of exception
        else:
            if self.in_transaction:
                self.commit()



#----------------------------------------------------------------------
def connect(dsn=None, user=None, password=None, host=None, database=None, port=None):
    connect_args = {}

    # Make an argument dict based off of the arguments passed.
    # If a DSN is given, we need to split it up.
    if dsn is not None:
        dsn_parts = dsn.split(';')
        for part in dsn_parts:
            part = part.strip()
            part_parts = part.split("=")
            if part_parts[0] not in ['host', 'user', 'password', 'database', 'port']:
                raise ValueError("Unrecognized parameter: {}".format(part_parts[0]))

            connect_args[part_parts[0]] = part_parts[1]

    # Convert DSN-provided port to int if present.
    if 'port' in connect_args:
        connect_args['port'] = int(connect_args['port'])

    # Explicit keyword arguments override DSN values.
    if password is not None:
        connect_args['password'] = password

    if host is not None:
        connect_args['host'] = host

    if user is not None:
        connect_args['user'] = user

    if database is not None:
        connect_args['database'] = database

    if port is not None:
        connect_args['port'] = int(port)

    # Only set the default port if none was provided via DSN or kwarg.
    connect_args.setdefault('port', 19812)

    if 'host' not in connect_args:
        # Need at least a host to connect to
        raise ValueError("Host name is required")

    for key in ['user', 'password', 'database']:
        if key not in connect_args:
            connect_args[key] = ""  # use an empty string if the argument is not provided. For example, if you don't need a user and password to log in.

    # Try to connect to the database
    fourd_connection = py4d_connection(**connect_args)

    return fourd_connection

