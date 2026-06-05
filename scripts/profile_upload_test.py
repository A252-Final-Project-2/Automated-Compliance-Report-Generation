"""
Quick smoke test to POST login and upload an avatar to /profile/upload-avatar.
Usage: python scripts/profile_upload_test.py --base http://localhost:5000 --username homeowner --password home123 --role homeowner --file path/to/avatar.png

This script uses only the Python standard library.
"""
import argparse
import sys
import os
from urllib import request as urllib_request
from http import cookiejar
import urllib.parse

try:
    import requests
except Exception:
    requests = None


def do_with_requests(base, username, password, role, filepath):
    s = requests.Session()
    # login
    login_url = base.rstrip('/') + '/login'
    r = s.post(login_url, data={'username': username, 'password': password, 'role': role})
    if r.status_code not in (200, 302):
        print('Login failed', r.status_code)
        return
    upload_url = base.rstrip('/') + '/profile/upload-avatar'
    with open(filepath, 'rb') as fh:
        r = s.post(upload_url, files={'avatar': fh})
    print('Upload status:', r.status_code)
    print(r.text[:400])


def do_no_requests(base, username, password, role, filepath):
    cj = cookiejar.CookieJar()
    opener = urllib_request.build_opener(urllib_request.HTTPCookieProcessor(cj))
    login_url = base.rstrip('/') + '/login'
    data = urllib.parse.urlencode({'username': username, 'password': password, 'role': role}).encode('utf-8')
    resp = opener.open(login_url, data)
    # upload multipart
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    CRLF = '\r\n'
    with open(filepath, 'rb') as fh:
        body = []
        body.append('--' + boundary)
        body.append('Content-Disposition: form-data; name="avatar"; filename="%s"' % os.path.basename(filepath))
        body.append('Content-Type: application/octet-stream')
        body.append('')
        body = CRLF.join(body).encode('utf-8') + CRLF.encode('utf-8') + fh.read() + CRLF.encode('utf-8')
        body += ('--' + boundary + '--' + CRLF).encode('utf-8')
        req = urllib_request.Request(base.rstrip('/') + '/profile/upload-avatar', data=body, method='POST')
        req.add_header('Content-Type', 'multipart/form-data; boundary=%s' % boundary)
        resp = opener.open(req)
        print('Upload status:', resp.getcode())
        print(resp.read(400).decode('utf-8', errors='ignore'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', required=True)
    p.add_argument('--username', required=True)
    p.add_argument('--password', required=True)
    p.add_argument('--role', required=True)
    p.add_argument('--file', required=True)
    args = p.parse_args()
    if not os.path.exists(args.file):
        print('File not found:', args.file)
        sys.exit(2)
    if requests:
        do_with_requests(args.base, args.username, args.password, args.role, args.file)
    else:
        do_no_requests(args.base, args.username, args.password, args.role, args.file)

if __name__ == '__main__':
    main()
