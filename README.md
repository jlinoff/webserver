# webserver
Simple python webserver than demonstrates GET/POST handling for HTTP/HTTPS

## Introduction

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
content from the current directory. To get a feeling for the
features available point it to the www directory that is included
in the repository.

   $ ./webserver.py --webdir www

This will start up an HTTP server listening on port 8080 for the local
host using the current directory as the root of the web directory
handling requests with the built in default request handler.

You can then view the output using favorite browser:

   $ firefox localhost:8080

See the specific examples in the help below for more details.

## Example 1. Getting Help

There is a lot of help available from the program itself.

```bash
$ ./webserver.py --help
```

## Example 2: HTTP server for current directory.

This shows the basic usage. It will create a server that
allows you to browse the current directory.

```bash
$ ./webserver.py
$ firefox http://localhost:8080  # client - in another window
```

## Example 3: HTTPS server for current directory on port 8443.

This shows how to run server as an HTTPS server using a self-signed
certificate.

```bash
$ # Create the self signed certificate.
$ openssl req \
     -subj '/CN=localhost/O=My Organization LTD/C=US/ST=Washington/L=Seattle' \
     -new -newkey rsa:2048 -days 365 -nodes -x509 -sha256 \
     -keyout server.key -out server.crt
$ cat server.crt server.key >server.pem
$ ./webserver.py --https --cert ./server.pem --port 8443
$ firefox http://localhost:8443  # client - in another window
```

## Example 4: HTTP server for a project directory.

This shows how to run the server for a specific project
directory.

```bash
$ ./webserver.py --webdir /opt/projects/mysite/www
$ firefox http://localhost:8080  # client - in another window
```

## Example 5: Daemon HTTP server for a project directory.

This shows how to run the server as daemon. For a production
system you would probably want to use something likesystemd or
supervisord to daemonize the process.

```bash
$ ./webserver.py \
      --webdir /opt/projects/mysite/www \
      --daemonize \
      --log-file /opt/projects/mysite/log/webserver.log \
      --pid-file /opt/projects/mysite/log/webserver.pid
$ firefox http://localhost:8080  # client - in another window
```

## Example 6: HTTP server for a project directory with custom plugin.

This example shows how to create a plugin using the -g (--generate)
option and use it. You can customize it to add all sorts of behavior.

```bash
$ mkdir -p /opt/projects/mysite/src
$ ./webserver.py -g >/opt/projects/mysite/src/plugin.py  # create the plug in
$ edit /opt/projects/mysite/src/plugin.py  # customize it
$ ./webserver.py \
      --webdir /opt/projects/mysite/www \
      --plugin /opt/projects/mysite/src/plugin.py \
      --extra 'plugin_param1=foobar'
$ firefox http://localhost:8080  # client - in another window
```

## Example 7: Full blown example for daemonized HTTPS server.

This is what a full blown example of a daemonized HTTPS server
might look.

```bash
$ ./webserver.py \
      --webdir /opt/projects/mysite/www \
      --plugin /opt/projects/mysite/src/plugin.py \
      --https \
      --cert /opt/projects/mysite/www/server.pem \
      --port 8443 \
      --daemonize \
      --log-file /opt/projects/mysite/log/webserver.log \
      --pid-file /opt/projects/mysite/log/webserver.pid
```

## Example 8. Full blown example of an HTTPS server for a service like systemd.

This example shows how you might run the webserver under a process
management tool like systemd or supervisord.

```bash
$ ./webserver.py \
      --webdir /opt/projects/mysite/www \
      --plugin /opt/projects/mysite/src/plugin.py \
      --https \
      --cert /opt/projects/mysite/www/server.pem \
      --port 8443
```

## Example 9. Show how templates work.

This example shows how templates work by filling three variables.

```bash
$ ./webserver.py --webdir www -L debug
$ firefox "http://localhost:8080/templates/test.tmpl?title=Templates&arg1=foo&arg2=42"  # client - in another window
```

## Plugins

Plugins are python modules that implement a callback function from the
server request handler. They provide you with complete control over how
the request data is processed. You can execute programs, access databases,
recognize dummy URLs, deal GET/POST data, fill in templates among other
things.

The default callback function name is request_handler(req) but you can
use another name if you wish. It accepts a single argument: the
request object which is derived from the
SimpleHTTPServer.SimpleHTTPRequestHandler). It has three additional
functions that let you access the server logger and the server
options:

1. res.ws_get_logger() - get the server logging object
2. res.ws_get_opts() - get the server options object
3. req.ws_get_url_prefix() - get the URL prefix

To see how to access the options take a look at the webserver_info()
function in the default_request_handler in webserver.py.

To see how to create custom URLs look at the special_case() function.

To see how templates work look at the templates() function.

You can create a plugin using the -g (or --generate) option. That is
the default plugin that is used if a custom plugin is not specified.

## Testing

The test subdirectory contains tests in the test.sh script. You must have
curl and wget installed for the tests to work.

To run the tests type: "./test.sh 2>&1|tee test.log". That will run the
tests and capture the output in test.log. If all of the tests pass you
will a summary that looks like this:

```bash
# ================================================================ #
# Done                                                             #
# ================================================================ #
Summary
   Passed:   9
   Failed:   0  
   Total:    9
```

## TODO

This is list of TODO items.

1. Convert to use python 3.
2. Add support for sessions.
3. Write an example that shows how to accept a username and password.

## Final Thoughts

I wrote this tool as a demonstration project to help me understand how
to use python to create a web server that can do cool things.

I hope that you find it helpful.
