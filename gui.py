"""Local graphical launcher. No web framework or extra packages required."""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
PREFIX = '@@GUI@@'


def configure_tool_path():
    """Include common per-user runtime locations for desktop launches."""
    locations = [Path.home() / '.deno' / 'bin']
    if sys.platform == 'darwin':
        locations.extend([Path('/opt/homebrew/bin'), Path('/usr/local/bin')])
    current = os.environ.get('PATH', '').split(os.pathsep)
    additions = [str(path) for path in locations if path.is_dir() and str(path) not in current]
    os.environ['PATH'] = os.pathsep.join(additions + current)


class LocalServer(ThreadingHTTPServer):
    # HTTPServer enables SO_REUSEADDR by default. On Windows that allows
    # multiple live servers to bind one port and randomly handle requests.
    allow_reuse_address = False

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def parse_urls(value):
    urls = list(dict.fromkeys(re.split(r'[,\s]+', value.strip())))
    if not urls or len(urls) > 100:
        raise ValueError('Paste between 1 and 100 YouTube links.')
    for url in urls:
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme not in ('http', 'https') or not (
            host in ('youtube.com', 'youtu.be') or host.endswith('.youtube.com')
        ) or not parsed.path.strip('/'):
            raise ValueError(f'Enter a complete YouTube link: {url}')
    return urls


def worker():
    from download import download_single_video
    config = json.loads(sys.stdin.readline())
    last = [0.0]

    def emit(data):
        print('\n' + PREFIX + json.dumps(data, ensure_ascii=True), flush=True)

    def progress(data):
        now = time.monotonic()
        if data.get('status') == 'downloading' and now - last[0] < .4:
            return
        last[0] = now
        total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
        info = data.get('info_dict') or {}
        emit({'event': 'progress', 'title': info.get('title', ''),
              'percent': round(min(100, data.get('downloaded_bytes', 0) / total * 100), 1) if total else None,
              'phase': 'Downloading' if data.get('status') == 'downloading' else 'Processing',
              'speed': data.get('speed'), 'eta': data.get('eta'),
              'item': info.get('playlist_index')})

    try:
        result = download_single_video(config['url'], config['folder'],
                                       audio_only=config['format'] == 'mp3',
                                       max_resolution=config['quality'], progress_hook=progress)
        emit({'event': 'result', **result})
    except Exception as error:
        emit({'event': 'result', 'success': False, 'message': str(error)})


class Dashboard:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = []
        self.processes = {}
        self.limit = 3
        self.folder = str(ROOT / 'downloads')
        self.maintenance = False
        self.stopping = False

    def state(self):
        with self.lock:
            return {'jobs': [dict(j) for j in self.jobs], 'folder': self.folder,
                    'maintenance': self.maintenance, 'tools': {
                        'FFmpeg': bool(shutil.which('ffmpeg')), 'Deno': bool(shutil.which('deno')),
                        'Downloader': __import__('importlib.util', fromlist=['find_spec']).find_spec('yt_dlp') is not None}}

    def add(self, data):
        urls = parse_urls(str(data.get('urls', '')))
        fmt = data.get('format', 'mp4')
        quality = data.get('quality')
        limit = int(data.get('workers', 3))
        if fmt not in ('mp4', 'mp3') or quality not in (None, 480, 720, 1080, 1440, 2160) or not 1 <= limit <= 5:
            raise ValueError('Choose a valid format, quality, and parallel download count.')
        if not shutil.which('ffmpeg'):
            raise ValueError('FFmpeg is missing. Install it and restart the dashboard.')
        folder = Path(str(data.get('folder') or self.folder)).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        with self.lock:
            if self.maintenance:
                raise ValueError('Wait for cleanup to finish.')
            if len(self.jobs) + len(urls) > 500:
                raise ValueError('Clear finished items before adding more downloads.')
            self.folder, self.limit = str(folder), limit
            for url in urls:
                self.jobs.append({'id': secrets.token_hex(8), 'url': url, 'title': url,
                                  'folder': str(folder), 'format': fmt, 'quality': quality,
                                  'status': 'Queued', 'phase': 'Waiting to start', 'percent': None,
                                  'logs': [], 'message': '', 'speed': None, 'eta': None})
            self.pump()

    def pump(self):
        # Caller holds lock; jobs are marked active before their threads start.
        if self.stopping:
            return
        active = sum(j['status'] == 'Active' for j in self.jobs)
        for job in self.jobs:
            if active >= self.limit:
                break
            if job['status'] == 'Queued':
                job.update(status='Active', phase='Reading video information')
                active += 1
                threading.Thread(target=self.run, args=(job,), daemon=True).start()

    def run(self, job):
        proc = None
        try:
            with self.lock:
                if job['status'] != 'Active':
                    return
                python = str(Path(sys.executable).with_name('python.exe')) if os.name == 'nt' else sys.executable
                proc = subprocess.Popen([python, '-u', str(ROOT / 'gui.py'), '--worker'],
                                        cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                        start_new_session=os.name != 'nt',
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                self.processes[job['id']] = proc
                proc.stdin.write(json.dumps(job) + '\n')
                proc.stdin.close()
            for line in proc.stdout:
                with self.lock:
                    if job['status'] == 'Cancelled':
                        continue
                    if PREFIX in line:
                        # Also tolerate messages from older workers whose
                        # terminal output did not end in a newline.
                        before, payload = line.split(PREFIX, 1)
                        if before.strip():
                            self.log(job, before)
                        event = json.loads(payload)
                        if event.pop('event') == 'progress':
                            if not event.get('title'):
                                event.pop('title', None)
                            job.update(event)
                        else:
                            job.update(status=('Skipped' if event.get('skipped') else 'Completed') if event['success'] else 'Failed',
                                       message=event['message'], phase='Finished', percent=100 if event['success'] else job['percent'])
                    elif line.strip():
                        self.log(job, line)
            proc.wait()
            with self.lock:
                if job['status'] == 'Active':
                    job.update(status='Failed', message='Downloader stopped unexpectedly. Check the activity log.')
        except Exception as error:
            with self.lock:
                if job['status'] != 'Cancelled':
                    job.update(status='Failed', message=str(error))
        finally:
            if proc and proc.poll() is None:
                self.terminate(proc)
            with self.lock:
                self.processes.pop(job['id'], None)
                self.pump()

    @staticmethod
    def log(job, line):
        job['logs'] = (job['logs'] + [re.sub(r'\x1b\[[0-9;]*m', '', line.strip())])[-80:]

    @staticmethod
    def terminate(proc):
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            # FFmpeg inherits the worker's session. Stop the whole group so
            # cancelling does not leave a merge/conversion running.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()

    def cancel(self, job_id):
        with self.lock:
            job = next((j for j in self.jobs if j['id'] == job_id), None)
            if not job:
                raise ValueError('Download no longer exists.')
            if job['status'] in ('Queued', 'Active'):
                job.update(status='Cancelled', phase='Stopped', message='Partial files are kept so you can resume later.')
                proc = self.processes.get(job_id)
                if proc:
                    self.terminate(proc)
                self.pump()

    def remove(self, job_id):
        """Stop and remove one queue entry without deleting downloaded files."""
        with self.lock:
            self.cancel(job_id)
            self.jobs = [job for job in self.jobs if job['id'] != job_id]

    def stop(self):
        with self.lock:
            self.stopping = True
            for job in list(self.jobs):
                self.cancel(job['id'])

    def cleanup(self):
        with self.lock:
            if self.maintenance or any(j['status'] in ('Queued', 'Active') for j in self.jobs):
                raise ValueError('Finish or cancel downloads before cleaning incomplete files.')
            self.maintenance = True
            folder = self.folder
        try:
            from cleanup_downloads import cleanup_incomplete_downloads
            removed, remaining = cleanup_incomplete_downloads(folder)
            return {'message': f'Removed {removed} incomplete files. {remaining} completed files remain.'}
        finally:
            with self.lock:
                self.maintenance = False


def serve(open_browser=True, port=8765):
    dashboard = Dashboard()
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, value, status=200, html=False):
            payload = value.encode() if html else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Streamline-App', 'youtube-downloader-v1')
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self):
            return self.headers.get('X-Dashboard-Token') == token and self.headers.get('Origin', base_url) == base_url

        def do_GET(self):
            if self.headers.get('Host') != urlparse(base_url).netloc:
                self.send({'error': 'Invalid host'}, 403)
                return
            if self.path == '/':
                self.send((ROOT / 'dashboard.html').read_text(encoding='utf-8').replace('__TOKEN__', token), html=True)
            elif self.path == '/api/state' and self.authorized():
                self.send(dashboard.state())
            else:
                self.send({'error': 'Not found'}, 404)

        def do_POST(self):
            if not self.authorized():
                self.send({'error': 'Unauthorized request'}, 403)
                return
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 65536:
                    raise ValueError('Request is too large or empty.')
                data = json.loads(self.rfile.read(size))
                result = {}
                if self.path == '/api/add':
                    dashboard.add(data)
                elif self.path == '/api/cancel':
                    dashboard.cancel(data['id'])
                elif self.path == '/api/remove':
                    dashboard.remove(data['id'])
                elif self.path == '/api/clear':
                    with dashboard.lock:
                        dashboard.jobs = [j for j in dashboard.jobs if j['status'] in ('Queued', 'Active')]
                elif self.path == '/api/folder':
                    folder = Path(str(data.get('folder') or dashboard.folder)).expanduser().resolve()
                    folder.mkdir(parents=True, exist_ok=True)
                    if os.name == 'nt':
                        os.startfile(str(folder))
                    else:
                        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(folder)])
                elif self.path == '/api/browse':
                    script = 'import tkinter as t; from tkinter import filedialog; r=t.Tk(); r.withdraw(); r.attributes("-topmost",True); print(filedialog.askdirectory(title="Choose downloads folder")); r.destroy()'
                    python = str(Path(sys.executable).with_name('python.exe')) if os.name == 'nt' else sys.executable
                    picked = subprocess.run([python, '-c', script], capture_output=True, text=True, encoding='utf-8',
                                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    if picked.returncode:
                        raise ValueError('The folder picker needs Tkinter. Install Python Tk support, or enter a folder path in Save to folder.')
                    result = {'folder': picked.stdout.strip()}
                elif self.path == '/api/cleanup':
                    result = dashboard.cleanup()
                elif self.path == '/api/shutdown':
                    dashboard.stop()
                    threading.Thread(target=server.shutdown, daemon=True).start()
                else:
                    self.send({'error': 'Not found'}, 404)
                    return
                self.send(result)
            except (ValueError, KeyError, OSError) as error:
                self.send({'error': str(error)}, 400)

    try:
        server = LocalServer(('127.0.0.1', port), Handler)
    except OSError:
        # Repeated double-clicks reopen the running app rather than creating
        # a second queue that could write to the same files.
        existing_url = f'http://127.0.0.1:{port}'
        try:
            with urlopen(existing_url, timeout=2) as response:
                existing = response.headers.get('X-Streamline-App') == 'youtube-downloader-v1'
        except OSError:
            existing = False
        if existing:
            if open_browser:
                webbrowser.open(existing_url)
            return
        server = LocalServer(('127.0.0.1', 0), Handler)
    base_url = f'http://127.0.0.1:{server.server_port}'
    print(base_url, flush=True)
    if open_browser:
        webbrowser.open(base_url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        dashboard.stop()


if __name__ == '__main__':
    configure_tool_path()
    if '--worker' in sys.argv:
        worker()
    else:
        try:
            serve(open_browser='--no-browser' not in sys.argv)
        except Exception as error:
            if os.name == 'nt':
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, str(error), 'Streamline could not start', 16)
            else:
                raise
