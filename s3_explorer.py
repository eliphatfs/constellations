import os
import sys
import time
import html
import boto3
import boto3.s3
import requests
import threading
from urllib.parse import urlparse, parse_qsl, quote, unquote
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

s3_endpoint = os.getenv("AWS_ENDPOINT_URL", "")
s3_bucket = sys.argv[-1] if len(sys.argv) > 1 else ""
s3_key = os.getenv("AWS_ACCESS_KEY_ID", "")
s3_secret = os.getenv("AWS_SECRET_ACCESS_KEY", "")
s3 = boto3.client('s3', endpoint_url=s3_endpoint, aws_access_key_id=s3_key, aws_secret_access_key=s3_secret)

dir_item = '<li class="list-group-item d-flex justify-content-between align-items-center"><a href="/?path={path}">{name}</a></li>'
file_item = '''
<li class="list-group-item d-flex justify-content-between align-items-center">
<span><a href="/{path}">{name}</a></span>
<span><span class="text-body-secondary me-4">{size}</span><a href="/share?path={path}&exp=600" class="badge text-bg-primary">Share</a></span>
</li>
'''.strip()
page_base_format = """
<!DOCTYPE html>
<html>
<head>
<title>S3 Explorer</title>
<meta charset="UTF-8">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxZW0iIGhlaWdodD0iMWVtIiB2aWV3Qm94PSIwIDAgMjQgMjQiPjxwYXRoIGZpbGw9IiM4ODg4ODgiIGQ9Ik01IDIxTDMgOWgxOGwtMiAxMnptNS02aDRxLjQyNSAwIC43MTMtLjI4OFQxNSAxNHQtLjI4OC0uNzEyVDE0IDEzaC00cS0uNDI1IDAtLjcxMi4yODhUOSAxNHQuMjg4LjcxM1QxMCAxNU02IDhxLS40MjUgMC0uNzEyLS4yODhUNSA3dC4yODgtLjcxMlQ2IDZoMTJxLjQyNSAwIC43MTMuMjg4VDE5IDd0LS4yODguNzEzVDE4IDh6bTItM3EtLjQyNSAwLS43MTItLjI4OFQ3IDR0LjI4OC0uNzEyVDggM2g4cS40MjUgMCAuNzEzLjI4OFQxNyA0dC0uMjg4LjcxM1QxNiA1eiIvPjwvc3ZnPg==">
<link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.3/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH" crossorigin="anonymous">
<script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.3/js/bootstrap.bundle.min.js" integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz" crossorigin="anonymous"></script>
</head>
<body>
<nav class="navbar navbar-expand-lg bg-body-tertiary">
  <div class="container">
    <a class="navbar-brand py-2" href="#">S3 EXPLORER</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarSupportedContent" aria-controls="navbarSupportedContent" aria-expanded="false" aria-label="Toggle navigation">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse py-2" id="navbarSupportedContent">
      <form class="d-flex" role="jump" method="get" action="/">
        <input class="form-control me-2" type="input" name="path" placeholder="Path" aria-label="Path">
        <button class="btn btn-outline-success" type="submit">Jump</button>
      </form>
    </div>
  </div>
</nav>
<div class="container">
<div class="py-2">
<div class="mt-4 mb-3 fs-4 text-body-secondary fw-light">Contents of <pre class="d-inline">{path}</pre></div>
<form class="d-flex my-3" role="filter" method="get" action="/">
  <input type="hidden" name="path" value="{path}">
  <input class="form-control me-2" type="input" name="filter" placeholder="Prefix Filter" value="{filter}" aria-label="Prefix Filter">
  <button class="btn btn-outline-success" type="submit">Apply</button>
</form>
<hr />
<ul class="list-group list-group-flush my-4">
  {dir_list}
</ul>
<form class="d-flex my-3" role="filter" method="get" action="/">
  <input type="hidden" name="path" value="{path}">
  <input type="hidden" name="filter" value="{filter}">
  <input type="hidden" name="marker" value="{marker}">
  <button class="btn btn-outline-success" type="submit" {nextdisabled}>Next Marker</button>
</form>
</div>
</div>
</body>
</html>
"""


def keepalive():
    while True:
        time.sleep(5)
        s3.head_bucket(Bucket=s3_bucket)


def sign_for_file(path, expire_time=600):
    return s3.generate_presigned_url('get_object',
                                     Params={'Bucket': s3_bucket,
                                             'Key': path},
                                     ExpiresIn=expire_time)


class S3Explorer(BaseHTTPRequestHandler):
    def do_GET(self):
        uri = urlparse(self.path)
        if uri.path == '/':
            qs = dict(parse_qsl(uri.query))
            p = qs.get('path', '/').strip('/')
            mainpath = p + '/'
            if len(p):
                p += '/'
            m = qs.get('marker', None)
            f = qs.get('filter', '')
            p += f
            if m is None:
                res = s3.list_objects_v2(
                    Bucket=s3_bucket,
                    Delimiter='/',
                    Prefix=p
                )
            else:
                res = s3.list_objects_v2(
                    Bucket=s3_bucket,
                    Delimiter='/',
                    Prefix=p,
                    ContinuationToken=m
                )
            data = []
            data.append(dir_item.format(path=quote(os.path.dirname(os.path.dirname(p))), name='..'))
            for item in res.get('CommonPrefixes', []):
                key = item['Prefix']
                qt = quote(key)
                name = html.escape(os.path.basename(os.path.dirname(key)) + '/')
                data.append(dir_item.format(path=qt, name=name))
            for item in res.get('Contents', []):
                key = item['Key']
                sz = item['Size']
                if sz > 1000 ** 3:
                    ss = '%.1f GB' % (sz / (1000 ** 3))
                elif sz > 1000 ** 2:
                    ss = '%.1f MB' % (sz / (1000 ** 2))
                elif sz > 1000 ** 1:
                    ss = '%.1f KB' % (sz / (1000 ** 1))
                else:
                    ss = '%d B' % sz
                qt = quote(key)
                name = html.escape(os.path.basename(key))
                data.append(file_item.format(path=qt, name=name, size=ss))
            nextdisabled = 'disabled'
            marker = ''
            if res['IsTruncated']:
                nextdisabled = ''
                marker = res['NextContinuationToken']
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(page_base_format.format(
                path=mainpath,
                marker=marker,
                nextdisabled=nextdisabled,
                filter=f,
                dir_list='\n'.join(data)
            ).encode())
        elif uri.path == '/share':
            qs = dict(parse_qsl(uri.query))
            p = qs.get('path', '/')
            e = int(qs.get('exp', '600'))
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(sign_for_file(p.strip("/"), e).encode())
        else:
            if 'Range' in self.headers:
                headers = {'Range': self.headers['Range']}
            else:
                headers = None
            key = sign_for_file(unquote(uri.path.strip("/")), 1800)
            resp = requests.get(key, headers=headers, stream=True, verify=os.getenv("AWS_CA_BUNDLE"))
            self.send_response(resp.status_code)
            # print(resp.headers['content-type'])
            for k, v in resp.headers.items():
                if k.lower() in ['etag', 'last-modified', 'date', 'server']:
                    continue
                if k.lower() == 'content-type' and v.lower() in ['application/octet-stream', 'application/x-sh']:
                    continue
                self.send_header(k, v)
            self.end_headers()
            for chunk in resp.iter_content(chunk_size=8192):  # Iterate over chunks
                if chunk:  # Filter out keep-alive new chunks
                    self.wfile.write(chunk)


if __name__ == '__main__':
    threading.Thread(target=keepalive, daemon=True).start()
    with ThreadingHTTPServer(('127.0.0.1', 9092), S3Explorer) as server:
        print("Serving at http://127.0.0.1:9092")
        server.serve_forever()
