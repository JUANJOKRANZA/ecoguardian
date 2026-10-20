import http.server,socketserver,os,sys
HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.join(HERE,'..','..','eco','web')
class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self,p):
        p=p.split('?')[0]
        if p in('/','/host.html'): return os.path.join(HERE,'host.html')
        return os.path.normpath(ROOT+p)
    def log_message(self,*a): pass
socketserver.TCPServer.allow_reuse_address=True
socketserver.ThreadingTCPServer(('127.0.0.1',8765),H).serve_forever()
