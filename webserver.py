#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
'''
Simple web server that demonstrates how browser/server interactions
work for HEAD, GET and POST requests using HTTP or HTTPS. It can be
customized using plugins.

This is an all-in-one solution. You do not need to separate out your
server from your code and you do not need a web server gateway
interface (WSGI). Just run this single program with a custom plugin.

It is not replacement for production systems. It is more of a
demonstration project that shows how all of the pieces fit together.

You can use it as a starting point to create a custom web server for
handling specific requests or for improving your understanding of how
web servers work but don't try to use it for any production work
unless it is for a simple, low traffic site.

It is very easy to use, simply run it and it will start serving
content from the current directory.

   $ ./webserver.py

This will start up an HTTP server listening on port 8080 for the local
host using the current directory as the root of the web directory
handling requests with the built in default request handler.

You can then view the output using favorite browser:

   $ firefox localhost:8080

See the specific examples in the help below for more usage details.

One interesting feature of this system is that is allows embedded
python in HTML modules. This allows dynamic web pages to be created.

Here is a very simple example:

    <!DOCTYPE HTML>
    <!-- python
      params = locals()
      params['title'] = 'Title of Page'
      params['arg1'] = 'foo'
      params['arg2'] = 42
    -->
    <html>
      <head>
        <meta charset="utf-8">
        <title>{title}</title>
      </head>
      <body>
        <pre>
         arg1 = {arg1}
         arg2 = {arg2}
        </pre>
      </body>
    </html>

As you can see, the python code defines the values of variables that
used in the HTML.

The format of the variables is the same that used for string.format()
operations (string.Formatter objects) so they are very flexible.

The embedded python can also reference other files. Here is an
example of how that works:

    <!DOCTYPE html>
    <!-- python
      # Define the variables used on the page using
      # the full power of python.
      # The params dictionary is defined by the
      # request handler.
      import datetime
      import os
      import sys

      def read_file(params, ifn):
        """
        Read a file.
        """
        try:
          ifn = os.path.join(params['sysdir'], ifn)
          with open(ifn, 'r') as ifp:
            return ifp.read()
        except IOError as exc:
          return 'Read failed for {0}: {1!r}.'.format(ifn, exc)

      params = locals()

      params['page_header'] = read_file(params, 'page_header.html')
      params['page_footer'] = read_file(params, 'page_footer.html')
      params['title'] = 'Template Test of Embedded Python'

      # This is referenced by the page_header after the substitution.
      params['date'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

      params['python_version'] = 'Python {0}.{1}.{2}'.format(sys.version_info[0],
                                                             sys.version_info[1],
                                                             sys.version_info[2])
      data = ''
      for i in range(5):
         data += '   {0} Count {0}\\n'.format(i)
      params['data'] = data[:-1]  # strip the last new line

      params['top'] = '<a href="/">Top</a>'
    -->
    <html>
      <head>
        <meta charset="utf-8">
        <title>Template Test</title>
        <link rel="icon" type="image/png" href="/webserver.png">
        <link href="/webserver.css" rel="stylesheet">
        <script src="/webserver.js"></script>
      </head>
      <body>
        <!-- page header (references {title} and {date}) -->
        {page_header}

        <!-- page body -->
        <pre>
    {python_version}

    Loop Data
    {data}
        </pre>
    {top}
        <!-- page footer -->
        {page_footer}
      </body>
    </html>

The python code will be left justified automatically but other than
that it must have proper indenting.
'''
from __future__ import print_function

# Compatibility testing.
import sys
pver = 'Python {0}.{1}.{2}'.format(sys.version_info[0],
                                   sys.version_info[1],
                                   sys.version_info[2])
if sys.version_info[0] == 3:
    # There are some known problems with
    # byte/string conversions.
    import http.server as HTTPServer
    sys.exit('Sorry, {0} is not supported.'.format(pver))
elif sys.version_info[0] == 2:
    if sys.version_info[0] == 2 and sys.version_info[1] < 7:
        sys.exit('Sorry, {0} is not supported. You must use Python 2.7 or later.'.format(pver))
    import SimpleHTTPServer as HTTPServer
else:
    sys.exit('Sorry, {0} is not supported.'.format(pver))
del pver

# Standard imports.
import argparse
import cgi
import Cookie
import datetime
import imp
import logging
import logging.handlers
import mimetypes
import random
import re
import os
import select
import socket
import SocketServer
import ssl
import string
import subprocess


VERSION = '1.0'


def logger_init(opts, name, level=logging.INFO):
    '''
    Create a basic logger with a stdout stream handler.
    '''
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(opts.log_format)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def logger_update(opts, logger):
    '''
    Update the logger to add a stream handler for the log
    file, if necessary. Also set the log level based on
    the user specification.
    '''
    level = {
        'critical': logging.CRITICAL,
        'debug': logging.DEBUG,
        'error': logging.ERROR,
        'info': logging.INFO,
        'notset': logging.NOTSET,
        'warning': logging.WARNING,
    }
    logger.setLevel(level[opts.log_level])

    if opts.log_file is not None and int(opts.log_size) > 0:
        # Create the handler for the log file.
        handler = logging.handlers.RotatingFileHandler(opts.log_file,
                                                       maxBytes=int(opts.log_size),
                                                       backupCount=int(opts.log_count))
        formatter = logging.Formatter(opts.log_format)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Capture all stdout and stderr output in the logger.
        class Logger:
            '''
            Create logger instances.
            '''
            def __init__(self, logger, prefix=''):
                self.logger = logger
                self.prefix = prefix

            def write(self, msg):
                self.logger(self.prefix + msg.rstrip())

            #def flush(self):
                #self.logger.flush()

        #logger.removeHandler(logger.handlers[0])  # remove the stdout handler
        sys.stdout = Logger(logger.info, 'stdout: ')  # redirect stdout
        sys.stderr = Logger(logger.info, 'stderr: ')  # redirect stderr

    return logger


def daemon_start(opts, logger):
    '''
    Start the daemon if the user requested that.
    '''
    if opts.daemonize is False:
        return

    if opts.log_file is None:
        logger.error('Log file must be specified to daemonize the process.')
        sys.exit(1)

    if opts.pid_file is None:
        logger.error('PID file must be specified to daemonize the process.')
        sys.exit(1)

    if os.path.exists(opts.pid_file) is True:
        logger.error('PID file exists, cannot daemonize.')
        sys.exit(1)

    # Make it a daemon process.
    # In practice it makes a lot more sense to use technologies
    # like systemd units or supervisord to daemonize the process
    # at the top level.
    if os.fork():
        sys.exit(0)  # exit the parent

    os.umask(0)
    os.setsid()

    if os.fork():
        sys.exit(0)  # exit the parent

    logger.info('Daemon started, PID={0}.'.format(os.getpid()))

    # disable stdin
    stdin = file('/dev/null', 'r')
    os.dup2(stdin.fileno(), sys.stdin.fileno())

    with open(opts.pid_file, 'w') as ofp:
        ofp.write('{0}'.format(os.getpid()))


def daemon_stop(opts, logger):
    '''
    Stop the daemon.
    '''
    if opts.daemonize is False:
        return

    logger.info('Daemon stopped, PID={0}.'.format(os.getpid()))
    if os.path.exists(opts.pid_file):
        os.remove(opts.pid_file)


def log_setup_info(opts, logger):
    '''
    Log setup information.
    Only in debug mode.
    '''
    logger.debug('Setup information.')
    entries = vars(opts)
    for key in sorted(entries, key=str.lower):
        logger.debug('   --{0:<12}  {1}'.format(key, entries[key]))
    cmd = []
    for arg in sys.argv:
        if arg.find(' ') >=0:
            arg = '"{0}"'.format(arg)
        cmd.append(arg)
    logger.debug('Cmd: {0}'.format(' '.join(cmd)))
    logger.debug('Python {0}.{1}.{2}'.format(sys.version_info[0],
                                             sys.version_info[1],
                                             sys.version_info[2]))


def getopts():
    '''
    Get the command line options.
    '''

    def cert_opt(val):
        '''
        Certificate file.
        It must exist.
        '''
        if os.path.exists(val) is False:
            raise argparse.ArgumentTypeError('Certificate file does not exist.')
        if os.path.isfile(val) is False:
            raise argparse.ArgumentTypeError('Certificate file is not a file.')
        return os.path.abspath(val)

    def entry_obj(val):
        '''
        Plugin module entry point.
        Must be a valid python function name.
        '''
        if re.search(r'^[a-zA-Z_][a-zA-Z_0-9]*$', val):
            return val
        raise argparse.ArgumentTypeError('Not a valid python function name.')

    def log_file_opt(val):
        '''
        Make sure that we have write permissions for this file.
        '''
        if os.path.exists(val):
            if os.path.isfile(val) is False:
                raise argparse.ArgumentTypeError('Log file is not a file.')
            if os.access(val, os.W_OK) is False:
                raise argparse.ArgumentTypeError('Log file is not writable.')
            return val


        dirpath = os.path.dirname(val)
        if dirpath == '':
            dirpath = '.'
        if os.path.exists(dirpath):
            if os.path.isdir(dirpath) is False:
                raise argparse.ArgumentTypeError('Log file directory is not a directory.')
            if os.access(dirpath, os.W_OK) is False:
                raise argparse.ArgumentTypeError('Log file directory is not writable.')
            return val

        try:
            os.makedirs(dirpath)
        except OSError as exc:
            raise argparse.ArgumentTypeError('Cannot create {0}: {1}'.format(dirpath, exc))
        return val

    def log_size_opt(val):
        '''
        Verify that the log size variable has the correct format.

        Size can be specified as the number of bytes or by using
        suffix: k=KB, m=MB, g=GB.

        Examples:
            Value       Num Bytes
            1048576     1048576
            1m          1048576
            1024k       1048576
            1073741824  1073741824
            1024m       1073741824
            1g          1073741824
        '''
        match = re.search(r'^(\d+)(\.\d+)?([kmg])?$', val)
        if match is None:
            raise argparse.ArgumentTypeError('Invalid format, expected something like "10m" or "1.3g".')
        else:
            if match.group(2) is not None:
                log_size = float(match.group(1) + match.group(2))
            else:
                log_size = int(match.group(1))

            if match.group(3) == 'k':
                log_size *= 2**10
            elif match.group(3) == 'm':
                log_size *= 2**20
            elif match.group(3) == 'g':
                log_size *= 2**30

            val = int(float(log_size))

        return val

    def plugin_opt(val):
        '''
        Python module plugin.
        '''
        if os.path.exists(val) is False:
            raise argparse.ArgumentTypeError('Plugin file does not exist.')
        if os.path.isfile(val) is False:
            raise argparse.ArgumentTypeError('Plugin file is not a file.')
        return os.path.abspath(val)

    def port_opt(val):
        '''
        Port number.
        Must be in the range [1..65535].
        '''
        try:
            ival = int(val)
            if 1 < ival < 65535:
                return ival
            raise argparse.ArgumentTypeError('Must be an integer in the range: [1..65535].')
        except ValueError:
            raise argparse.ArgumentTypeError('Not an integer in the range: [1..65535].')
        return ival

    def pid_file_opt(val):
        '''
        Make sure that we have write permissions for this file
        and the process isn't already running.
        '''
        def process_running(pid):
            '''
            Does the process exist?
            '''
            try:
                os.kill(pid, 0)
            except OSError:
                return False  # not running
            else:
                return True  # running

        if os.path.exists(val):
            # If the PID file exists, determine whether the process is
            # running. If it is, we are done. If it isn't, clean up.
            pid = ''
            with open(val, 'r') as ifp:
                pid = ifp.read()
            pid.strip()
            if re.search(r'^\d+$', pid):
                if process_running(int(pid)):
                    raise argparse.ArgumentTypeError('Pid file exists, cannot continue.')
                else:
                    if os.access(val, os.W_OK) is False:
                        raise argparse.ArgumentTypeError('Pid file cannot be removed, cannot continue.')
                    os.remove(val)  # Try to remove it
            else:
                raise argparse.ArgumentTypeError('Pid file exists and has invalid data, cannot continue.')
        else:
            # Make sure that the file is writable.
            dirpath = os.path.dirname(val)
            if dirpath == '':
                dirpath = '.'
            if os.path.exists(dirpath):
                if os.path.isdir(dirpath) is False:
                    raise argparse.ArgumentTypeError('PID file directory is not a directory.')
                if os.access(dirpath, os.W_OK) is False:
                    raise argparse.ArgumentTypeError('PID file directory is not writable.')
            else:
                try:
                    os.makedirs(dirpath)
                except OSError as exc:
                    raise argparse.ArgumentTypeError('Cannot create {0}: {1}'.format(dirpath, exc))

        return os.path.abspath(val)

    def webdir_opt(val):
        '''
        Verify that the webdir exists and is readable.
        '''
        if os.path.exists(val) is False:
            raise argparse.ArgumentTypeError('Web directory does not exist.')
        if os.path.isdir(val) is False:
            raise argparse.ArgumentTypeError('Web directory is not a directory.')
        if os.access(val, os.W_OK) is False:
            raise argparse.ArgumentTypeError('Web directory is not readable.')
        return os.path.abspath(val)

    # Trick to capitalize the built-in headers.
    # Unfortunately I can't get rid of the ":" reliably.
    def gettext(s):
        lookup = {
            'usage: ': 'USAGE:',
            'optional arguments': 'OPTIONAL ARGUMENTS',
            'show this help message and exit': 'Show this help message and exit.\n ',
        }
        return lookup.get(s, s)

    # Get the help from the module documentation.
    argparse._ = gettext  # to capitalize help headers
    base = os.path.basename(sys.argv[0])
    name = os.path.splitext(base)[0]
    usage = '\n  {0} [OPTIONS]'.format(base)
    desc = 'DESCRIPTION:{0}'.format('\n  '.join(__doc__.split('\n')))
    epilog = r'''
EXAMPLES:
  $ # ================================
  $ # Example 1: help
  $ {0} --help

  $ # ================================
  $ # Example 2: Console HTTP server for current directory.
  $ {0}
  $ firefox http://localhost:8080  # client - in another window

  $ # ================================
  $ # Example 3: Console HTTPS server for current directory on port 8443.
  $ #            First create the self signed certificate.
  $ openssl req \
       -subj '/CN=localhost/O=My Organization LTD/C=US/ST=Washington/L=Seattle' \
       -new -newkey rsa:2048 -days 365 -nodes -x509 -sha256 \
       -keyout server.key -out server.crt
  $ cat server.crt server.key >server.pem
  $ {0} --https --cert ./server.pem --port 8443
  $ firefox http://localhost:8443  # client - in another window

  $ # ================================
  $ # Example 4: Console HTTP server for a project directory.
  $ {0} --webdir /opt/projects/mysite/www
  $ firefox http://localhost:8080  # client - in another window

  $ # ================================
  $ # Example 5: Daemon HTTP server for a project directory.
  $ {0} \
        --webdir /opt/projects/mysite/www \
        --daemonize \
        --log-file /opt/projects/mysite/log/webserver.log \
        --pid-file /opt/projects/mysite/log/webserver.pid
  $ firefox http://localhost:8080  # client - in another window

  $ # ================================
  $ # Example 6: Console HTTP server for a project directory with custom plugin.
  $ mkdir -p /opt/projects/mysite/src
  $ {0} -g >/opt/projects/mysite/src/plugin.py  # create the plug in
  $ edit /opt/projects/mysite/src/plugin.py  # customize it
  $ {0} \
        --webdir /opt/projects/mysite/www \
        --plugin /opt/projects/mysite/src/plugin.py \
        --extra 'plugin_param1="foobar"'
  $ firefox http://localhost:8080  # client - in another window

  $ # ================================
  $ # Example 7: Full blown example for daemonized HTTPS server.
  $ {0} \
        --webdir /opt/projects/mysite/www \
        --plugin /opt/projects/mysite/src/plugin.py \
        --https \
        --cert /opt/projects/mysite/www/server.pem \
        --port 8443 \
        --daemonize \
        --log-file /opt/projects/mysite/log/webserver.log \
        --pid-file /opt/projects/mysite/log/webserver.pid

  $ # ================================
  $ # Example 8: Full blown example for HTTPS server
  $ #            under process management (e.g. systemd).
  $ {0} \
        --webdir /opt/projects/mysite/www \
        --plugin /opt/projects/mysite/src/plugin.py \
        --https \
        --cert /opt/projects/mysite/www/server.pem \
        --port 8443
 '''.format(base)
    afc = argparse.RawTextHelpFormatter
    parser = argparse.ArgumentParser(formatter_class=afc,
                                     description=desc[:-2],
                                     usage=usage,
                                     epilog=epilog)

    parser.add_argument('-c', '--cert',
                        action='store',
                        type=cert_opt,
                        metavar=('FILE'),
                        default=None,
                        help=r'''HTTPS certificate file.
Here is how you could create simple, self signed certificate:
   $ openssl req \
     -subj '/CN=localhost/O=My Organization LTD/C=US/ST=Washington/L=Seattle' \
     -new -newkey rsa:2048 -days 365 -nodes -x509 -sha256 \
     -keyout server.key -out server.crt
   $ cat server.crt server.key >server.pem
Default=%(default)s.
 ''')


    parser.add_argument('-d', '--daemonize',
                        action='store_true',
                        help='''Daemonize the server.

You must specify a PID file (--pid=file) and a log file (--log-file).

Note that for a system service you would not use this option. Instead
you would use something like systemd or supervisord to daemonize the
process for you.
Default=%(default)s (console mode).
 ''')

    parser.add_argument('-e', '--entry',
                        action='store',
                        type=entry_obj,
                        default='request_handler',
                        help='''The entry point for the plug-in module (--plugin).
It is a module level function named 'request_handler' that accepts the
request object and displays the page information.

The request object is derived from SimpleHTTPServer.SimpleHTTPRequestHandler
with a few additional methods.

   ws_get_logger()     Get the logger object (derived from the python logging module).
   ws_get_opts()       Get the argparse options object.
   ws_get_url_prefix() Get the protocol, domain and port (e.g. https://localhost:8080)

Default=%(default)s.
 ''')

    parser.add_argument('-g', '--generate',
                        action='store_true',
                        help='''Generate an example plug-in module to stdout and exit.
You can use it to bootstrap a custom plug-in.
Default=%(default)s.
 ''')

    parser.add_argument('-H', '--host',
                        action='store',
                        type=str,
                        default='localhost',
                        metavar=('NAME'),
                        help='''Hostname.
This can also be an IP address.
Default=%(default)s.
 ''')

    parser.add_argument('--https',
                        action='store_true',
                        help=r'''Run in secure HTTPS mode.
You must specify a certificate file for HTTPS using -c or --cert.
Default=%(default)s.
 ''')

    parser.add_argument('-l', '--log-file',
                        action='store',
                        type=log_file_opt,
                        default=None,
                        metavar=('FILE'),
                        help='''Log file.
If you specify a log file, all output will be redirected to it.
Default=%(default)s (no log file).
 ''')

    parser.add_argument('--log-format',
                        action='store',
                        type=str,
                        default='%(asctime)s %(filename)s %(levelname)-7s %(lineno)5d %(message)s',
                        metavar=('FORMAT'),
                        help='''The log format.
The logger uses the python logging package which defines the formatting options.
Default='%(default)s'.
 ''')

    parser.add_argument('--log-count',
                        action='store',
                        type=int,
                        default=4,
                        metavar=('COUNT'),
                        help='''The maximum number of rollover log files.
Default=%(default)s.
 ''')

    parser.add_argument('--log-size',
                        action='store',
                        type=log_size_opt,
                        default='10m',
                        metavar=('SIZE'),
                        help='''The maximum size of the log file before rollover.
Acceptable suffixes: k=KB, m=MB, g=GB.
Examples: 1048576, 1m, 1024k, 1g
Default=%(default)s.
 ''')

    parser.add_argument('-L', '--log-level',
                        action='store',
                        type=str,
                        default='info',
                        metavar=('LEVEL'),
                        choices=['notset', 'debug', 'info', 'warning', 'error', 'critical',],
                        help='''Define the logging level.
Choices=%(choices)s.
Default=%(default)s.
 ''')

    parser.add_argument('-p', '--port',
                        action='store',
                        type=port_opt,
                        default=8080,
                        help='''Port.
Default=%(default)s.
 ''')

    parser.add_argument('-P', '--plugin',
                        action='store',
                        type=plugin_opt,
                        default=None,
                        metavar=('PYTHON_MODULE'),
                        help='''Python plugin module.
This is the python plugin module that contains the entry point for
processing requests. The entry point is a module level function name
'request_handler' that accepts the request object and displays the
page information. The entry point name can be changed using the
--entry option.

If a plugin is not specified, the default behavior is to display the
file specified. If a directory is specified, it will look for an
index.html file. If the index.html file is found, it is displayed. If
it is not found, the directory is displayed with linkable file names
and subdirectories,

Default=%(default)s (no plugin).
 ''')

    parser.add_argument('-q', '--pid-file',
                        action='store',
                        type=pid_file_opt,
                        default=None,
                        metavar=('FILE'),
                        help='''PID file.
This file is used when daemonizing the process.
Default=%(default)s (no PID file).
 ''')

    parser.add_argument('-V', '--version',
                        action='version',
                        version='%(prog)s v' + VERSION[0],
                        help="""Show program's version number and exit.
 """)

    parser.add_argument('-w', '--webdir',
                        action='store',
                        type=webdir_opt,
                        default=os.path.abspath('.'),
                        metavar=('DIR'),
                        help='''The web root directory that contains the HTML/CSS/JS files.
Default=%(default)s (current directory).
 ''')

    parser.add_argument('-x', '--extra',
                        action='append',
                        type=str,
                        metavar=('STRING'),
                        help='''Extra arguments for custom plugins.
You can have as many extra arguments as you want.
The interpretation is up to the plugin.
The default plug-in ignores them.
Default=%(default)s.
''')

    opts = parser.parse_args()

    return opts, name


def default_request_handler(req):
    '''
    This is the default request handler.

    It is not meant for production but it shows how flexible the
    system is. Here is how it behaves.

    If the path is a file, then it displays it.
    If the path is a directory, it looks for index.html.
    If index.html exists, it displays it.
    If index.html does not exist, it displays the directory contents
    with links.

    There is a special URL '/webserver/info' that displays
    webserver information. Here is an example:

        http://localhost:8080/webserver/info

    There is another special URL '/system/name' that executes
    'uname -a' and returns the results.

    There is yet another special URL '/redirect/to/...' that redirects
    to another URL. It demonstrates that special URLs can have
    arguments. Here are two examples. The first one redirects to an
    external website. The second redirects to an internal page.

        http://localhost:8080/redirect/to/https/google.com --> https://google.com
        http://localhost:8080/redirect/to/webserver.html --> /webserver.html

    If a directory URL has a '@' suffix, the directory contents are
    displayed even if an index.html file is present. Here is an
    example:

        http://localhost:8080/@

    If a file URL has a '@' suffix, the file contents are
    displayed. Here is an example:

        http://localhost:8080/index.html@

    If a file URL has a '!' suffix, it is executed and the results are
    returned. You can control how the contents are displayed by
    specifying a content-type argument. Here some examples:

        http://localhost:8080/scripts/script.sh!
        http://localhost:8080/scripts/script.sh!?content-type=text/plain
        http://localhost:8080/scripts/script.sh!?content-type=text/html

    If a file has a '.tmpl' extension it is a template that uses the
    python string.Formatter syntax to fill in variables by name from
    the GET/POST parameters. Here is an example:

        http://localhost:8080/templates/test.tmpl?titleMy%20Title&arg1=Foo7arg2=23.

    Templates can also embed python code directly with the HTML to
    provide a lot of flexibility. See the www/templates/example.tmpl
    template to see how it works.

    The variables in the template are {title}, {arg1} and {arg2}.

    This implementation shows the server has the following key features:

        1. It can fill in defaults (index.html).
        2. It can handle special URLS (/webserver/info).
        3. It can perform special operations (@).
        4. It can execute local tools (!).
        5. It can support templates.
    '''
    def elapsed(dts, now=None):
        '''
        Get the elapsed time in seconds.
        '''
        if now is None:
            now = datetime.datetime.now()
        elapsed = now - dts
        secs = int(elapsed.total_seconds())
        return secs

    def expired(dts, max_secs, now=None):
        '''
        Has this datetime stamp expired?
        '''
        return elapsed(dts) > max_secs

    def init_globals(opts):
        '''
        This is where the ws_globals global variable is defined.
        This global variable contains general webserver data for
        all sessions.
        '''
        global ws_globals
        if 'ws_globals' not in globals():
            ws_globals = {}

            # Add in the "extra" variables from the
            # --extra or -x command line options.
            if opts.extra is not None:
                for extra in opts.extra:
                    key, val = extra.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    if re.search(r'^\d+$', val):
                        ws_globals[key] = int(val)
                    elif re.search(r'^(\d+)?\.\d+$', val) or re.search(r'^(\d+)\.', val):
                        ws_globals[key] = float(val)
                    elif val.lower() == 'true':
                        ws_globals[key] = True
                    elif val.lower() == 'false':
                        ws_globals[key] = False
                    else:
                        ws_globals[key] = val

    def init(req, opts, logger):
        '''
        Initialize after request.

        It creates the following attributes:
           req.m_urlpath   base url path
           req.m_syspath   system path
           req.m_protocol  HTTP or HTTPS
           req.m_params    GET/POST parameters
        '''
        # Initialize the globals.
        init_globals(opts)

        # Parse the GET options.
        if req.path.find('?') >= 0:
            parts = req.path.split('?')
            params = cgi.parse_qs(parts[1])
            urlpath = parts[0]
        else:
            params = {}
            urlpath = req.path

        # Parse the POST options.
        if req.command == 'POST':
            assert len(params) == 0
            ctype, pdict = cgi.parse_header(req.headers.getheader('content-type'))
            if ctype == 'multipart/form-data':
                params = cgi.parse_multipart(req.rfile, pdict)
            elif ctype == 'application/x-www-form-urlencoded':
                length = int(req.headers['content-length'])
                data = req.rfile.read(length)
                params = cgi.parse_qs(data, keep_blank_values=1)

            # some browser send 2 more bytes
            rdy, _, _ = select.select([req.connection], [], [], 0)
            if rdy:
                req.rfile.read(2)

        # Get the system path and the root path.
        syspath = req.translate_path(urlpath)
        sysroot = syspath[:-len(urlpath)]

        # Get the protocol.
        protocol = 'HTTPS' if opts.https else 'HTTP'
        setattr(req, 'm_urlpath', urlpath)   # http://localhost:8080/foo/bar?a=b --> /foo/bar
        setattr(req, 'm_syspath', syspath)   # system path, file or dir
        setattr(req, 'm_sysroot', sysroot)   # system path to the root directory
        setattr(req, 'm_params', params)     # parameters from GET or POST
        setattr(req, 'm_protocol', protocol) # HTTP or HTTPS
        setattr(req, 'm_headers', [])        # additional headers

        # Look for cookies so that we can set up the Set-Cookie response.
        # If cookies exist, use them.
        # If cookies do not exit, create a cookies entry.
        if req.headers.has_key('cookie'):
            cookie = Cookie.SimpleCookie(req.headers.getheader('cookie'))
        else:
            cookie = Cookie.SimpleCookie()

        key = 'ws_sid'  # cookie id
        if cookie.has_key(key):
            sid = cookie[key].value
        else:
            sid = ''.join(random.choice(string.ascii_letters + string.digits) for i in range(16))
            cookie[key] = sid

        setattr(req, 'm_cookie', cookie)
        setattr(req, 'm_sid', sid)  # session id

        # Debug messages.
        if opts.log_level == 'debug':
            logger.debug('Handling {0} {1} request {2}'.format(req.m_protocol,
                                                               req.command,
                                                               req.path))
            logger.debug('   UrlPath  : {0}'.format(req.m_urlpath))
            logger.debug('   SysPath  : {0}'.format(req.m_syspath))
            logger.debug('   SysRoot  : {0}'.format(req.m_sysroot))
            logger.debug('   Params   : {0!r}'.format(req.m_params))
            logger.debug('   SessionId: {0}'.format(req.m_sid))

            logger.debug('HTTP Headers')
            entries = vars(req)
            headers = str(entries['headers']).replace('\r\n', '\\r\\n\n')
            for header in headers.split('\n'):
                if len(header):  # skip zero length headers
                    logger.debug('   {0} {1}'.format(len(header), header))

    def nocache(req):
        '''
        Define nocache headers.
        '''
        if len([x for x in req.m_headers if x[0] == 'Cache-Control']) is False:
            req.m_headers.append(('Cache-Control', 'no-cache, no-store, must-revalidate'))  # HTTP 1.1
            req.m_headers.append(('Pragma', 'no-cache'))  # HTTP 1.0
            req.m_headers.append(('Expires', '0'))  # HTTP 1.0 proxies

    def send(req, ctype, out):
        '''
        Send the page.
        '''
        req.send_response(200)
        req.send_header('Content-type', ctype)
        req.send_header('Content-length', len(out))

        # Cookies - this always resets all of the cookies.
        for morsel in req.m_cookie.values():  # SimpleCookie object.
            req.send_header('Set-Cookie', morsel.output(header='').lstrip())

        # Extra headers like those for no-caching.
        for header in req.m_headers:
            req.send_header(header[0], header[1])

        req.end_headers()

        req.wfile.write(out)

    def escape_text(text):
        '''
        Escape text for HTML presentation.
        '''
        tbl = {'&': '&amp;',
               '"': '&quot;',
               "'": '&apos;',
               '>': '&gt;',
               '<': '&lt;',}
        return ''.join(tbl.get(c, c) for c in text)

    def webserver_info(req, opts, logger):
        '''
        Report some webserver information.
        '''
        lines = []
        lines.append('<!DOCTYPE HTML>')
        lines.append('<html>')
        lines.append('  <head>')
        lines.append('    <meta charset="utf-8">')
        lines.append('    <title>Webserver - Directory</title>')
        lines.append('  </head>')
        lines.append('  <body>')
        lines.append('    <pre>')
        lines.append('Configuration Options')

        entries = vars(opts)
        for key in sorted(entries, key=str.lower):
            val = entries[key]
            lines.append('   --{0:<12} {1}'.format(key, val))

        lines.append('')

        lines.append('Server Information')
        entries = vars(req)
        for key in sorted(entries, key=str.lower):
            val = entries[key]
            text = escape_text(str(val)).replace('\r\n', '\\r\\n\n')
            if text.find('\n'):
                text = '\n                    '.join(text.split('\n'))
                text = text.rstrip()
            lines.append('   {0:<16} {1}'.format(key, text))

        lines.append('    </pre>')
        lines.append('  </body>')
        lines.append('</html>')

        out = '\n'.join(lines)
        send(req, 'text/html', out)

    def runcmd(cmd):
        '''
        Run a command with a lot of output.
        '''
        proc = subprocess.Popen(cmd,
                                shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)

        # Read the output 1 character at a time so that it can be
        # displayed in real time.
        text = ''
        while not proc.returncode:
            data = proc.stdout.read(32)
            if not data:
                break # all done, wait for returncode to get populated
            text += data.decode('utf-8')
        proc.wait()
        return proc.returncode, text

    def redirect(req, opts, logger, url):
        '''
        Redirect to the login page.
        '''
        logger.debug('REDIRECT: "{0}".'.format(url))
        req.send_response(301)
        req.send_header('Location', url)

        # Cookies - this always resets all of the cookies.
        for morsel in req.m_cookie.values():  # SimpleCookie object.
            req.send_header('Set-Cookie', morsel.output(header='').lstrip())

        req.end_headers()

    def define_template_parameters(req):
        '''
        Define the template parameters.
        '''
        # Setup the parameters.
        params = {}
        for key in req.m_params:
            val = req.m_params[key][0]
            params[key] = val

        # Load other useful parameters.
        if os.path.isdir(req.m_syspath):
            params['sysdir'] = req.m_syspath
            params['urldir'] = req.m_urlpath
        else:
            params['sysdir'] = os.path.dirname(req.m_syspath)
            params['urldir'] = os.path.dirname(req.m_urlpath)

        params['urlprefix'] = req.ws_get_url_prefix()
        params['sid'] = req.m_sid  # session id
        return params


    def compile_template(data, depth=8):
        '''
        Compile a template with embedded python code.

        The python code sits between <!-- python and --> statements.
        It sets the parameter values so that they can be used
        for variable substitution.
        '''
        params = define_template_parameters(req)

        # Find all of the python fragments.
        # <!-- python
        #   # Set the variables here.
        #   params = locals()
        #   params['title'] = 'Template Test of Embedded Python'
        # -->
        fragments = re.findall(r'<!-- python(.*?)-->', data, flags=re.DOTALL | re.MULTILINE)
        if len(fragments) == 0:
            html = data
            if re.search(r'[^{][{][^}]+[}][^}]', html):
                html = html.format(**params)
        else:
            # Load up all of the fragments to get all of the
            # parameters.
            for fragment in fragments:
                # left justify so that statements are in the leftmost column.
                min_indent = min(map(len, re.findall('^([ ]+)', fragment, re.MULTILINE)))
                fragment = re.sub('^[ ]{' + str(min_indent) + '}', '', fragment, flags=re.MULTILINE)
                exec(fragment, globals(), params)

            # Remove the python fragments.
            html = re.sub(r'<!-- python.*?-->\s*\n?', '', data, flags=re.DOTALL | re.MULTILINE).strip()

            # Substitute the values for the variables.
            # This must be done multiple times because
            # there may be variables defined in nested
            # files.
            html = html.format(**params)
            for i in range(depth):
                if not re.search(r'[^{][{][^}]+[}][^}]', html):
                    break
                html = html.format(**params)

        return html

    def template(req, logger, ext='.tmpl'):
        '''
        Simple template handling using the built in string.Formatter
        class.

        If you specify a file that looks like this:

           <!DOCTYPE HTML>
           <html>
             <head>
               <meta charset="utf-8">
               <title>{title}</title>
             </head>
             <body>
               <pre>
                arg1 = {arg1}
                arg2 = {arg2}
               </pre>
             </body>
           </html>

        The variables are enclosed in braces.
        You can then specify GET/POST parameters to populate those
        variables.

        For example, if the file name is test.tmpl (for template), you
        could navigate to the page using GET parameters as follows:

            "http://localhost:8080/test.tmpl?title=Template%20Title&arg1=FooBar&arg2=23".

        When the server sees ".tmpl" files, it will automatically
        substitute the values and display the result.

        You can also embed python directly into the template to set
        the variables. Here is a simple example:

           <!DOCTYPE HTML>
           <!-- python
             params = locals()
             params['title'] = 'Title of Page'
             params['arg1'] = 'foo'
             params['arg2'] = 42
           -->
           <html>
             <head>
               <meta charset="utf-8">
               <title>{title}</title>
             </head>
             <body>
               <pre>
                arg1 = {arg1}
                arg2 = {arg2}
               </pre>
             </body>
           </html>

        You can also read in nested files with variables and
        fill them in. See www/templates/example.tmpl for a
        more complex example.

        The data in the template python code will override
        the URL parameters.
        '''
        if req.m_urlpath.endswith(ext) is False:
            return False

        # This is a template.
        # Do the substitution and display the results.
        logger.debug('TEMPLATE: "{0}".'.format(req.m_syspath))
        try:
            with open(req.m_syspath, 'r') as ifp:
                out = ifp.read()
            out = compile_template(out)
            send(req, 'text/html', out)
        except IOError:
            req.send_error(404, 'Not found')
        except KeyError as exc:
            # At least one of the arguments is not
            # defined. Display the result as plain
            # text.
            out = '<!-- ERROR: {0!r} -->\n{1}'.format(exc, out)
            send(req, 'text/plain', out)
        return True

    def display_directory(req):
        '''
        Display the directory listing with active links.
        '''
        # The directory exists but there is no index.html file in it.
        # Display a directory listing.
        lines = []
        lines.append('<!DOCTYPE HTML>')
        lines.append('<html>')
        lines.append('  <head>')
        lines.append('    <meta charset="utf-8">')
        lines.append('    <title>Webserver - Directory</title>')
        lines.append('  </head>')
        lines.append('  <body>')
        lines.append('    <pre>')
        lines.append(req.m_syspath + '\n')

        if req.m_urlpath != '/':
            # If this is not the top level URL path, allow
            # the user to backup using '..'.
            if req.m_urlpath[-1] == '/':
                # This avoids the problem of '//' which resets the path.
                urlppath = os.path.dirname(req.m_urlpath)
            urlppath = os.path.dirname(req.m_urlpath)
            fname = '..'
            fsize = 0
            ftype = 'dir'
            lines.append('{0:>10}  {1:<4}  <a href="{2}">{3}</a>'.format(fsize, ftype, urlppath, fname))

        for fname in sorted(os.listdir(req.m_syspath), key=str.lower):
            sysfile = os.path.join(req.m_syspath, fname)
            fsize = os.path.getsize(sysfile)
            ftype = 'dir' if os.path.isdir(sysfile) is True else 'file'
            if req.m_urlpath[-1] == '/':
                link = req.m_urlpath + fname
            else:
                link = req.m_urlpath + '/' + fname
            lines.append('{0:>10}  {1:<4}  <a href="{2}">{3}</a>'.format(fsize, ftype, link, fname))

        lines.append('    </pre>')
        lines.append('  </body>')
        lines.append('</html>')

        out = '\n'.join(lines)
        send(req, 'text/html', out)

    def display_file(req, opts, logger, path):
        '''
        Display the file specified by the path
        argument.

        If it is HTML, allow embedded python code.
        '''
        # Load the file data.
        ctype = req.guess_type(path)
        if ctype in ['application/x-sh', ]:
            ctype = 'text/plain'  # fix .sh
        logger.debug('Content type is "{0}".'.format(ctype))
        
        try:
            mode = 'r' if ctype.startswith('text/') else 'rb'
            with open(path, mode) as ifp:
                out = ifp.read()

            # Allow embedded python in HTML code.
            if ctype == 'text/html':
                out = compile_template(out)

            # Create the page.
            send(req, ctype, out)
        except IOError as exc:
            req.send_error(404, 'File not found {0}'.format(exc))

    def url_webinfo(req, opts, logger):
        '''
        Special dispatched URL: /webserver/info.
        '''
        webserver_info(req, opts, logger)

    def url_sysname(req, opts, logger):
        '''
        Special dispatched URL: /system/name.
        '''
        # run uname -a, capture the output and display it
        sts, out = runcmd('uname -a')
        send(req, 'text/plain', out)

    def url_redirect1(req, opts, logger, path):
        '''
        Special dispatched URL: /redirect/to/...
        '''
        redirect(req, opts, logger, path)

    def url_redirect2(req, opts, logger, prefix, path):
        '''
        Special dispatched URL: /redirect/to/...
        '''
        url = '{0}://{1}'.format(prefix, path)
        redirect(req, opts, logger, url)

    def url_dir(req, opts, logger, path):
        '''
        Special dispatched URL: .*@.

        If '@' appears at the end of a directory, generate a directory
        listing even if an index.html is present.

        If '@' appears at the end of the file, dump the file contents
         as plain text.
        '''
        req.m_syspath = req.m_syspath[:-1]
        req.m_urlpath = req.m_urlpath[:-1]

        if os.path.exists(req.m_syspath) is False:
            req.send_error(404, 'Not found')
        elif os.path.isdir(req.m_syspath):
            display_directory(req)
        elif os.path.isfile(req.m_syspath):
            try:
                with open(req.m_syspath, 'r') as ifp:
                    out = ifp.read()
                send(req, 'text/plain', out)
            except IOError:
                req.send_error(404, 'Not found')
        else:
            req.send_error(404, 'Not found')

    def url_exec(req, opts, logger, path):
        '''
        Special dispatched URL: .*!.
        '''
        # If '!' appears at the end of the path, execute
        # the file and display the output in the format
        # specified by the content-type parameter on the
        # URL.
        #
        # If the content-type parameter is not specified
        # then display the output as plain text.
        #
        # Here is an example:
        #   localhost:8080/scripts/make_page.sh?content-type=text/html
        if 'content-type' in req.m_params:
            ctype = req.m_params['content-type'][0]
        else:
            ctype = 'text/plain'

        req.m_syspath = req.m_syspath[:-1]
        req.m_urlpath = req.m_urlpath[:-1]

        if os.path.isfile(req.m_syspath):
            sts, out = runcmd(req.m_syspath)
            send(req, ctype, out)
        else:
            req.send_error(404, 'Not found: "{0}"'.format(req.m_syspath))

    def url_general_dispatch(req, opts, logger):
        '''
        General dispatcher.
        '''
        # If control reaches this point, this is not a special
        # case, the user specified a directory or file to
        # handle.
        if os.path.exists(req.m_syspath) is False:
            req.send_error(404, 'Not found {0}'.format(req.m_syspath))  # path must exist
            return

        if os.path.isdir(req.m_syspath) is True:
            # This is a directory.
            # See if index files are there.
            sysfile = None
            for index in ['index.html', 'index.htm', 'default.htm', ]:
                path = os.path.join(req.m_syspath, index)
                if os.path.exists(path) is True:
                    sysfile = path
                    break

            # Special case, if this is a directory with no
            # index files, display the directory contents.
            if sysfile is None:
                display_directory(req)
                return

            req.m_syspath = sysfile

        # Process templates or non-templates.
        if template(req, logger) is False:
            display_file(req, opts, logger, req.m_syspath)

    def url_dispatcher(req, opts, logger):
        '''
        Dispatch the special urls to functions.
        '''
        global ws_globals
        logger.debug('REQUEST PATH {0}'.format(req.path))

        if 'url_dispatch' not in ws_globals:
            # Add in the url dispatches for the 'special' URLs.
            # This is done here to avoid re-compiling them every
            # time a request is handled.
            # The first argument is the URL pattern to match.
            # The second argument is the name of the dispatch function.
            # The dispatch function has 3 fixed arguments plus the arguments
            # defined in the re.
            # Example:
            #    (re.compile('/foo/([^/]+)/([^/]+)/?'), 'url_func'), # <-- dispatch: 2 args: arg1, arg2
            #
            #    def url_func(req, opts, logger, arg1, arg2): ...
            ws_globals['url_dispatch'] = (
                (re.compile(r'^/webserver/info/?$'), url_webinfo),
                (re.compile(r'^/system/name/?$'), url_sysname),
                (re.compile('^/redirect/to/(https?)/(.+)$'), url_redirect2),
                (re.compile('^/redirect/to(/.+)$'), url_redirect1),
                (re.compile('^(.+)@$'), url_dir),
                (re.compile('^(.+)!$'), url_exec),
            )

        for dispatch in ws_globals['url_dispatch']:
            regex = dispatch[0]
            function = dispatch[1]  # function name
            match = regex.search(req.m_urlpath)
            logger.debug('URL_DISPATCH DEBUG "{0}" "{1}" "{2}"'.format(req.m_urlpath, regex.pattern, function.__name__))
            if match:
                args = match.groups()
                kwargs = match.groupdict()
                logger.debug('URL DISPATCH "{0}" "{1}".'.format(function.__name__, req.m_urlpath))
                function(req, opts, logger, *args, **kwargs)
                return

        url_general_dispatch(req, opts, logger)

    # Main.
    logger = req.ws_get_logger()
    opts = req.ws_get_opts()
    init(req, opts, logger)
    # nocache(req)  # test
    url_dispatcher(req, opts, logger)


def get_request_handler(opts, logger):
    '''
    Load the plugin to get the request handler.

    If a plugin was not specified, then use the default_request_handler.
    '''
    if opts.plugin is None:
        return default_request_handler

    if os.path.exists(opts.plugin) is False:
        logger.error('Plugin file does not exist: "{0}".'.format(opts.plugin))
        sys.exit(1)
    module_name = os.path.splitext(os.path.basename(opts.plugin))[0]
    module = imp.load_source(module_name, opts.plugin)
    function = getattr(module, opts.entry)
    return function


def create_request_handler_class(opts, logger, request_handler):
    '''
    Factory to make the request handler and add arguments to it.

    It exists to provide custom handling for the requests and to allow
    the handler to access the opts and logger variables locally.
    '''
    class RequestHandler(HTTPServer.SimpleHTTPRequestHandler):
        '''
        Factory generated request handler class that contain
        additional class variables.
        '''
        s_opts = opts
        s_logger = logger
        allow_reuse_address = True

        def ws_get_opts(self):
            '''
            Provide the options.
            '''
            return RequestHandler.s_opts

        def ws_get_logger(self):
            '''
            Provide the logger.
            '''
            return RequestHandler.s_logger

        def ws_get_url_prefix(self):
            '''
            Get the url prefix.

            Example: http://localhost:8080
            '''
            opts = RequestHandler.s_opts
            protocol = 'http' if opts.https is False else 'https'
            prefix = '{0}://{1}:{2}'.format(protocol, opts.host, opts.port)
            return prefix

        def do_GET(self):
            '''
            Handle a get request.
            '''
            request_handler(self)

        def do_POST(self):
            '''
            Handle a get request.
            '''
            request_handler(self)

    return RequestHandler


def serve(opts, logger, request_handler):
    '''
    Run the webserver until the user types ^C or the process is
    killed.
    '''
    if opts.https is True and opts.cert is None:
        logger.error('HTTPS must have a cert file (--cert).')
        sys.exit(1)
    if opts.https is False and opts.cert is not None:
        logger.warning('Cert file specified but --https was not specified, did you mean to specify --https?')

    try:
        RequestHandlerClass = create_request_handler_class(opts, logger, request_handler)
        port = int(opts.port)
        server = SocketServer.TCPServer((opts.host, port), RequestHandlerClass)
    except socket.error as exc:
        logger.error('Failed to start server {0}:{1}: {2}'.format(opts.host, port, exc))
        sys.exit(1)

    protocol = 'HTTP'
    if opts.https:
        server.socket = ssl.wrap_socket(server.socket, certfile=opts.cert, server_side=True)
        protocol += 'S'


    logger.info('Listening on {0}:{1} for {2} requests.'.format(opts.host, opts.port, protocol))
    os.chdir(opts.webdir)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('Keyboard interrupt.')

    try:
        server.shutdown()
        server.server_close()
    except Exception as exc:
        logger.error('Server shutdown failed: {0!r}.'.format(exc))


def generate(opts):
    '''
    Generate the default plugin module by parsing this source file.
    '''
    if opts.generate is False:
        return

    with open(sys.argv[0], 'r') as ifp:
        lines = ifp.readlines()

    flag = False
    for line in lines:
        line = line.rstrip()
        if line.find('def default_request_handler') == 0:
            line = line.replace('def default_request_handler', 'def request_handler')
            flag = True
            print("'''")
            print('# Default request handler.')
            print("'''")
            print('import Cookie')
            print('import cgi')
            print('import datetime')
            print('import mimetypes')
            print('import os')
            print('import random')
            print('import re')
            print('import select')
            print('import string')
            print('import subprocess')
            print('')
        elif line.find('def ') == 0:
            flag = False
        if flag:
            print(line)

    sys.exit(0)


def main():
    '''
    Main entry point.
    '''
    opts, name = getopts()
    generate(opts)

    logger = logger_init(opts, name)
    logger = logger_update(opts, logger)

    logger.info('********************************')
    logger.info('Starting the server.')
    request_handler = get_request_handler(opts, logger)
    log_setup_info(opts, logger)
    daemon_start(opts, logger)
    serve(opts, logger, request_handler)
    daemon_stop(opts, logger)
    logger.info('Stopping the server.')


if __name__ == '__main__':
    main()

