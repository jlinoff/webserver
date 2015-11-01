'''
# Default request handler.
'''
import Cookie
import cgi
import mimetypes
import os
import random
import re
import select
import string
import subprocess

def request_handler(req):
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

    def init(req, opts, logger):
        '''
        Initialize after request.

        It creates the following attributes:
           req.m_urlpath   base url path
           req.m_syspath   system path
           req.m_protocol  HTTP or HTTPS
           req.m_params    GET/POST parameters
        '''
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

        # Get the protocol.
        protocol = 'HTTPS' if opts.https else 'HTTP'
        setattr(req, 'm_urlpath', urlpath)   # http://localhost:8080/foo/bar?a=b --> /foo/bar
        setattr(req, 'm_syspath', req.translate_path(urlpath))  # system path, file or dir
        setattr(req, 'm_params', params)     # parameters from GET or POST
        setattr(req, 'm_protocol', protocol) # HTTP or HTTPS

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
            logger.debug('   Params   : {0!r}'.format(req.m_params))
            logger.debug('   SessionId: {0}'.format(req.m_sid))

            logger.debug('HTTP Headers')
            entries = vars(req)
            headers = str(entries['headers']).replace('\r\n', '\\r\\n\n')
            for header in headers.split('\n'):
                if len(header):  # skip zero length headers
                    logger.debug('   {0} {1}'.format(len(header), header))

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

        req.end_headers()

        req.wfile.write(out)

    def display_directory(syspath, urlpath):
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
        lines.append(syspath + '\n')

        if urlpath != '/':
            # If this is not the top level URL path, allow
            # the user to backup using '..'.
            if urlpath[-1] == '/':
                urlppath = os.path.dirname(urlpath)
            urlppath = os.path.dirname(urlpath)
            fname = '..'
            fsize = 0
            ftype = 'dir'
            lines.append('{0:>10}  {1:<4}  <a href="{2}">{3}</a>'.format(fsize, ftype, urlppath, fname))

        for fname in sorted(os.listdir(syspath), key=str.lower):
            sysfile = os.path.join(syspath, fname)
            fsize = os.path.getsize(sysfile)
            ftype = 'dir' if os.path.isdir(sysfile) is True else 'file'
            if urlpath[-1] == '/':
                link = urlpath + fname
            else:
                link = urlpath + '/' + fname
            lines.append('{0:>10}  {1:<4}  <a href="{2}">{3}</a>'.format(fsize, ftype, link, fname))

        lines.append('    </pre>')
        lines.append('  </body>')
        lines.append('</html>')

        out = '\n'.join(lines)
        send(req, 'text/html', out)

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

    def special_case(res, opts, logger):
        '''
        Handle special case URLs.
        '''
        # Check for special URLs.
        if re.search(r'^/webserver/info/?$', req.m_urlpath):
            # This is a special dummy path that tells the handler to
            # report information about the server.
            logger.debug('SPECIAL CASE: /webserver/info.')
            webserver_info(req, opts, logger)
            return True
        elif re.search(r'^/system/name/?$', req.m_urlpath):
            # This is a special dummy path that tells the handler to
            # report the system name.
            logger.debug('SPECIAL CASE: /system/name.')
            sts, out = runcmd('uname -a')
            send(req, 'text/plain', out)
            return True
        elif re.search(r'^/redirect/to/.*$', req.m_urlpath):
            # This is a special dummy path that tells the handler to
            # redirect to the specified URL.
            # If the first part is http/ or https/ it will
            # be converted to https:// otherwise it is treated as
            # an abs path from the root of the web directory.
            # Examples:
            #    /redirect/to/https/google.com --> https://google.com
            #    /redirect/to/webserver.html   --> /webserver.html
            url = req.m_urlpath[len('/redirect/to'):]
            url = re.sub(r'^/(http)(s)?/', r'\1\2://', url)
            logger.debug('REDIRECT: "{0}.'.format(url))
            req.send_response(301)
            req.send_header('Location', url)

            # Cookies - this always resets all of the cookies.
            for morsel in req.m_cookie.values():  # SimpleCookie object.
                req.send_header('Set-Cookie', morsel.output(header='').lstrip())

            req.end_headers()
            return True
        elif re.search(r'@$', req.m_urlpath):
            # If '@' appears at the end of a directory, generate a directory
            # listing even if an index.html is present.
            # If '@' appears at the end of the file, dump the file contents
            # as plain text.
            logger.debug('SPECIAL CASE: @ (directory listing or file contents).')
            req.m_syspath = req.m_syspath[:-1]
            req.m_urlpath = req.m_urlpath[:-1]
            if os.path.exists(req.m_syspath) is False:
                req.send_error(404, 'Not found')
            elif os.path.isdir(req.m_syspath):
                display_directory(req.m_syspath, req.m_urlpath)
            elif os.path.isfile(req.m_syspath):
                try:
                    with open(req.m_syspath, 'r') as ifp:
                        out = ifp.read()
                    send(req, 'text/plain', out)
                except IOError:
                    req.send_error(404, 'Not found')
            else:
                req.send_error(404, 'Not found')
            return True
        elif re.search(r'!$', req.m_urlpath):
            # If '!' appears at the end of the path, execute
            # the file and display the output in the format
            # specified by the content-type parameter.
            # If the content-type parameter is not specified
            # then display the output as plain text.
            # Example:
            if 'content-type' in req.m_params:
                ctype = req.m_params['content-type'][0]
            else:
                ctype = 'text/plain'
            logger.debug('SPECIAL CASE: ! ({0})'.format(ctype))
            req.m_syspath = req.m_syspath[:-1]
            req.m_urlpath = req.m_urlpath[:-1]
            if os.path.isfile(req.m_syspath):
                sts, out = runcmd(req.m_syspath)
                send(req, ctype, out)
            else:
                req.send_error(404, 'Not found: "{0}"'.format(req.m_syspath))
            return True
        return False

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

    # Main.
    logger = req.ws_get_logger()
    opts = req.ws_get_opts()
    init(req, opts, logger)
    if special_case(req, opts, logger):
        return

    # If control reaches this point, this is not a special
    # case, the user specified a directory or file to
    # handle.
    if os.path.exists(req.m_syspath) is False:
        req.send_error(404, 'Not found')  # path must exist
        return

    if os.path.isdir(req.m_syspath) is True:
        # This is a directory.
        # See if index files are there.
        sysfile = None
        for index in ['index.html', 'index.html']:
            path = os.path.join(req.m_syspath, index)
            if os.path.exists(path) is True:
                sysfile = path
                break

        # Special case, if this is a directory with no
        # index files, display the directory contents.
        if sysfile is None:
            display_directory(req.m_syspath, req.m_urlpath)
            return

        req.m_syspath = sysfile

    # Process templates.
    if template(req, logger) is True:
        return

    # Get the content type.
    ctype = req.guess_type(req.m_syspath)
    if ctype in ['application/x-sh', ]:
        ctype = 'text/plain'  # fix .sh
    logger.debug('Content type is "{0}".'.format(ctype))

    # Load the file data.
    try:
        mode = 'r' if ctype.startswith('text/') else 'rb'
        with open(req.m_syspath, mode) as ifp:
            out = ifp.read()

        # Allow embedded python in HTML code.
        if ctype == 'text/html':
            out = compile_template(out)

        # Create the page.
        send(req, ctype, out)
    except IOError:
        req.send_error(404, 'File not found')


