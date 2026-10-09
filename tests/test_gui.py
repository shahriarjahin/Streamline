"""Dashboard tests without network access or real media downloads."""
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import signal
import subprocess

from gui import Dashboard, LocalServer, PREFIX, parse_urls
from http.server import BaseHTTPRequestHandler


class TestDashboard(unittest.TestCase):
    def test_unix_cancellation_stops_ffmpeg_process_group(self):
        process = Mock(pid=12345)
        with patch('gui.os.name', 'posix'), patch('gui.os.killpg', create=True) as kill_group:
            Dashboard.terminate(process)
        kill_group.assert_called_once_with(12345, signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=5)

    def test_unix_cancellation_force_stops_an_unresponsive_group(self):
        process = Mock(pid=12345)
        process.wait.side_effect = [subprocess.TimeoutExpired('worker', 5), 0]
        # SIGKILL is not defined on Windows; supply the POSIX value when
        # checking the Unix branch on the Windows test host.
        with patch('gui.os.name', 'posix'), patch('gui.os.killpg', create=True) as kill_group, patch('gui.signal.SIGKILL', 9, create=True):
            Dashboard.terminate(process)
        self.assertEqual(kill_group.call_count, 2)
        self.assertEqual(kill_group.call_args_list[0].args, (12345, signal.SIGTERM))
        self.assertEqual(kill_group.call_args_list[1].args, (12345, 9))

    def test_second_server_cannot_share_the_live_port(self):
        first = LocalServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
        try:
            with self.assertRaises(OSError):
                LocalServer(first.server_address, BaseHTTPRequestHandler)
        finally:
            first.server_close()

    def test_rejects_disguised_hosts_and_non_http_urls(self):
        for url in ('https://youtube.com.evil.example/watch?v=x',
                    'https://evilyoutube.com/watch?v=x', 'file://youtube.com/watch?v=x'):
            with self.assertRaises(ValueError):
                parse_urls(url)

    def test_accepts_shorts_and_deduplicates(self):
        url = 'https://www.youtube.com/shorts/abc'
        self.assertEqual(parse_urls(f'{url}, {url}'), [url])

    def test_queue_limits_workers_and_cancelled_queue_never_starts(self):
        dashboard = Dashboard()
        with tempfile.TemporaryDirectory() as folder, patch('gui.shutil.which', return_value='ffmpeg'), patch('gui.threading.Thread') as thread:
            dashboard.add({'urls': 'https://youtu.be/a https://youtu.be/b https://youtu.be/c',
                           'folder': folder, 'workers': 1})
            self.assertEqual([j['status'] for j in dashboard.jobs], ['Active', 'Queued', 'Queued'])
            dashboard.cancel(dashboard.jobs[1]['id'])
            self.assertEqual(thread.call_count, 1)
            self.assertEqual(dashboard.jobs[1]['status'], 'Cancelled')
            with self.assertRaises(ValueError):
                dashboard.cleanup()

    def test_worker_progress_result_and_logs_reach_dashboard(self):
        dashboard = Dashboard()
        job = {'id': 'test', 'status': 'Active', 'logs': [], 'percent': None}
        dashboard.jobs.append(job)
        progress = {'event': 'progress', 'title': 'A video', 'percent': 42, 'speed': 100, 'eta': 9}
        result = {'event': 'result', 'success': True, 'message': 'Saved'}

        class Process:
            stdin = io.StringIO()
            stdout = io.StringIO('Reading information\n' + PREFIX + json.dumps(progress) + '\n' + PREFIX + json.dumps(result) + '\n')
            def wait(self):
                return 0
            def poll(self):
                return 0

        with patch('gui.subprocess.Popen', return_value=Process()):
            dashboard.run(job)
        self.assertEqual(job['status'], 'Completed')
        self.assertEqual(job['title'], 'A video')
        self.assertEqual(job['logs'], ['Reading information'])
        self.assertEqual(job['percent'], 100)
        self.assertEqual(dashboard.processes, {})

    def test_progress_embedded_after_terminal_output_is_parsed(self):
        dashboard = Dashboard()
        job = {'id': 'mixed', 'status': 'Active', 'logs': [], 'percent': None}
        dashboard.jobs.append(job)
        progress = {'event': 'progress', 'percent': 27.8, 'speed': 2185328, 'eta': 286}
        result = {'event': 'result', 'success': False, 'message': 'Test finished'}

        class Process:
            stdin = io.StringIO()
            stdout = io.StringIO('[download] 27.8% ETA 04:46' + PREFIX + json.dumps(progress) + '\n' + PREFIX + json.dumps(result) + '\n')
            def wait(self):
                return 0
            def poll(self):
                return 0

        with patch('gui.subprocess.Popen', return_value=Process()):
            dashboard.run(job)
        self.assertEqual(job['percent'], 27.8)
        self.assertEqual(job['speed'], 2185328)
        self.assertEqual(job['eta'], 286)
        self.assertFalse(any(PREFIX in line for line in job['logs']))

    def test_remove_active_item_stops_process_and_keeps_files(self):
        dashboard = Dashboard()
        with tempfile.TemporaryDirectory() as folder, patch('gui.shutil.which', return_value='ffmpeg'), patch('gui.threading.Thread'):
            from pathlib import Path
            partial = Path(folder, 'video.mp4.part')
            partial.write_bytes(b'resume data')
            dashboard.add({'urls': 'https://youtu.be/a', 'folder': folder})
            job_id = dashboard.jobs[0]['id']
            process = object()
            dashboard.processes[job_id] = process
            with patch.object(dashboard, 'terminate') as terminate:
                dashboard.remove(job_id)
                terminate.assert_called_once_with(process)
            self.assertEqual(dashboard.jobs, [])
            self.assertEqual(partial.read_bytes(), b'resume data')

    def test_remove_queued_and_finished_items(self):
        dashboard = Dashboard()
        dashboard.jobs = [{'id': 'queued', 'status': 'Queued'}, {'id': 'done', 'status': 'Completed'}]
        dashboard.stopping = True
        with patch.object(dashboard, 'terminate') as terminate:
            dashboard.remove('queued')
            dashboard.remove('done')
            terminate.assert_not_called()
        self.assertEqual(dashboard.jobs, [])

    def test_shutdown_does_not_start_waiting_downloads(self):
        dashboard = Dashboard()
        dashboard.jobs = [{'id': 'active', 'status': 'Active'}, {'id': 'waiting', 'status': 'Queued'}]
        with patch('gui.threading.Thread') as thread:
            dashboard.stop()
            thread.assert_not_called()
        self.assertEqual([job['status'] for job in dashboard.jobs], ['Cancelled', 'Cancelled'])


if __name__ == '__main__':
    unittest.main()
