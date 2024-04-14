import os
import sys
import html
import boto3
import boto3.s3
from urllib.parse import urlparse, parse_qsl, quote, unquote
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

s3_endpoint = os.getenv("AWS_ENDPOINT_URL", "")
s3_bucket = sys.argv[-1] if len(sys.argv) > 1 else ""
s3_key = os.getenv("AWS_ACCESS_KEY_ID", "")
s3_secret = os.getenv("AWS_SECRET_ACCESS_KEY", "")
s3 = boto3.client('s3', endpoint_url=s3_endpoint, aws_access_key_id=s3_key, aws_secret_access_key=s3_secret)

dir_item = '<li class="list-group-item d-flex justify-content-between align-items-center"><a href="/?path={path}">{name}</a></li>'
file_item = '<li class="list-group-item d-flex justify-content-between align-items-center"><a href="/{path}">{name}</a><a href="/share?path={path}&exp=600" class="badge text-bg-primary">Share</a></li>'
page_base_format = """
<!DOCTYPE html>
<html>
<head>
<title>S3 Explorer</title>
<meta charset="UTF-8">
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
                qt = quote(key)
                name = html.escape(os.path.basename(key))
                data.append(file_item.format(path=qt, name=name))
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
            self.send_response(200)
            self.end_headers()
            s3.download_fileobj(s3_bucket, unquote(uri.path.strip("/")), self.wfile)


if __name__ == '__main__':
    with ThreadingHTTPServer(('127.0.0.1', 9092), S3Explorer) as server:
        print("Serving at http://127.0.0.1:9092")
        server.serve_forever()
