import sys
sys.path.append('/var/www/rikstermbanken/src/')

from rikstermbanken import app as application

#def application(env, start_response):
#    try:
#        from rikstermbanken import app
#    except Exception as e:
#        err = e
#    start_response("200 OK", [("Content-Type","text/html")])
#    return [repr(err).encode("utf-8")]
