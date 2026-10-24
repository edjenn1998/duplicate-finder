import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import DuplicateFinder as app
from PIL import Image


class EngineRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        for name in ('a.txt', 'b.txt', 'c.txt'):
            (self.source / name).write_text('same contents')
        self.group = app.scan(self.source, minimum=0)[0][0]

    def test_cancel_on_last_progress_discards_results(self):
        cancel = threading.Event()
        def progress(phase, *args):
            if phase == 'Finished':
                cancel.set()
        with self.assertRaises(app.Cancelled):
            app.scan(self.source, cancel=cancel, progress=progress)

    def test_zero_byte_duplicates_are_opt_in(self):
        for name in ('zero1', 'zero2'):
            (self.source / name).touch()
        self.assertEqual(len(app.scan(self.source)[0]), 1)
        self.assertEqual(len(app.scan(self.source, minimum=0)[0]), 2)

    def test_explicit_symlink_root_is_resolved(self):
        link = self.root / 'chosen-link'
        link.symlink_to(self.source, target_is_directory=True)
        self.assertEqual(len(app.scan(link)[0][0]), 3)

    def test_queued_directory_replaced_by_symlink_is_not_followed(self):
        nested = self.source / 'nested'
        nested.mkdir()
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'secret1').write_text('outside')
        (outside / 'secret2').write_text('outside')
        original = os.lstat
        replaced = False
        def racing_lstat(path, *a, **kw):
            nonlocal replaced
            if Path(path) == nested and not replaced:
                nested.rmdir()
                nested.symlink_to(outside, target_is_directory=True)
                replaced = True
            return original(path, *a, **kw)
        with patch('os.lstat', racing_lstat):
            groups, _, counts = app.scan(self.source)
        self.assertTrue(replaced)
        self.assertEqual(len(groups), 1)
        self.assertEqual(counts['symlinks'], 1)

    def test_cancel_during_copy_removes_staging_and_retains_source(self):
        target = self.group[0]
        destination = self.root / 'holding'
        destination.mkdir()
        cancel = threading.Event()
        original = app.checkpoint
        def checkpoint(token):
            if any(destination.iterdir()):
                cancel.set()
            original(token)
        with patch.object(app, 'checkpoint', checkpoint):
            with self.assertRaises(app.Cancelled):
                app.act(target, self.group, self.group[1:], 'move', str(destination), cancel)
        self.assertTrue(Path(target.path).exists())
        self.assertFalse(list(destination.iterdir()))

    def test_final_name_is_not_visible_until_complete(self):
        destination = self.root / 'holding'
        destination.mkdir()
        original = app.publish_copy
        calls = []
        def inspect(staged, dest):
            self.assertFalse(dest.exists())
            self.assertEqual(staged.read_bytes(), b'same contents')
            self.assertTrue(Path(self.group[0].path).exists())
            calls.append(True)
            return original(staged, dest)
        with patch.object(app, 'publish_copy', inspect):
            result = app.act(self.group[0], self.group, self.group[1:], 'move', str(destination))
        self.assertEqual(calls, [True])
        self.assertEqual(Path(result).read_bytes(), b'same contents')
        self.assertEqual(len(list(destination.iterdir())), 1)

    def test_no_atomic_publication_support_preserves_source(self):
        destination = self.root / 'holding'
        destination.mkdir()
        with patch.object(app, 'publish_copy', side_effect=OSError('unsupported filesystem')):
            with self.assertRaises(OSError):
                app.act(self.group[0], self.group, self.group[1:], 'move', str(destination))
        self.assertTrue(Path(self.group[0].path).exists())
        self.assertFalse(list(destination.iterdir()))

    def test_hard_link_fallback_never_overwrites(self):
        src, dest = self.root / 'new', self.root / 'exists'
        src.write_text('new'); dest.write_text('original')
        with patch.object(app.sys, 'platform', 'darwin'):
            with self.assertRaises(FileExistsError):
                app.publish_copy(src, dest)
        self.assertEqual(dest.read_text(), 'original')

    def test_space_estimate_counts_hardlinks_correctly(self):
        path = self.source / 'alias'
        os.link(self.group[0].path, path)
        group = app.scan(self.source)[0][0]
        linked = [e for e in group if e.links > 1]
        self.assertEqual(app.reclaimable_bytes(linked[:1]), 0)
        self.assertEqual(app.reclaimable_bytes(linked), linked[0].size)
        selected = app.select_extra_paths([group])
        self.assertFalse(any(e.path in selected for e in linked))

    def test_oldest_and_newest_keep_policies(self):
        for index, entry in enumerate(self.group):
            os.utime(entry.path, ns=(1000 + index, 1000 + index))
        group = app.scan(self.source)[0][0]
        newest = app.select_extra_paths([group], 'Newest')
        oldest = app.select_extra_paths([group], 'Oldest')
        self.assertNotIn(str(self.source / 'c.txt'), newest)
        self.assertNotIn(str(self.source / 'a.txt'), oldest)
        self.assertEqual(len(newest), 2)

    def test_csv_handles_unicode_and_commas(self):
        import csv
        import io
        entry = app.Entry('/folder/日本語,photo.png', self.group[0].identity, 'abc')
        rows = list(csv.reader(io.StringIO(app.scan_csv([[entry]], {entry.path}))))
        self.assertEqual(rows[1][1], 'Remove')
        self.assertEqual(rows[1][-1], entry.path)

    def test_preview_refuses_changed_file_symlink_and_fifo(self):
        entry = self.group[0]
        Path(entry.path).write_text('changed')
        with self.assertRaises(ValueError):
            app.read_preview(entry)
        Path(entry.path).unlink()
        Path(entry.path).symlink_to(self.group[1].path)
        with self.assertRaises((ValueError, OSError)):
            app.read_preview(entry)
        Path(entry.path).unlink()
        os.mkfifo(entry.path)
        with self.assertRaises(ValueError):
            app.read_preview(entry)

    def test_cmyk_and_utf16_previews(self):
        path = self.source / 'cmyk.jpg'
        with Image.new('CMYK', (200, 300), (0, 100, 0, 0)) as image:
            image.save(path)
        digest, identity, links = app.hash_checked(path)
        _, picture = app.read_preview(app.Entry(str(path), identity, digest, links), 50, 60)
        with picture:
            self.assertEqual(picture.mode, 'RGB')
            self.assertLessEqual(picture.width, 50)
            self.assertLessEqual(picture.height, 60)
        path = self.source / 'utf16.txt'
        path.write_text('Unicode preview 日本語', encoding='utf-16')
        digest, identity, links = app.hash_checked(path)
        content, picture = app.read_preview(app.Entry(str(path), identity, digest, links))
        self.assertIn('日本語', content)
        self.assertIsNone(picture)

    def test_external_viewer_does_not_inherit_frozen_libraries(self):
        process = Mock()
        process.wait.return_value = 0
        with patch.object(app.sys, 'frozen', True, create=True), \
             patch.dict(os.environ, {'LD_LIBRARY_PATH': '/bundle', 'LD_LIBRARY_PATH_ORIG': '/original', 'TK_LIBRARY': '/bundle/tk'}), \
             patch.object(app.subprocess, 'Popen', return_value=process) as launch:
            app.open_external('/file with spaces.txt')
        env = launch.call_args.kwargs['env']
        self.assertEqual(env['LD_LIBRARY_PATH'], '/original')
        self.assertNotIn('TK_LIBRARY', env)
        self.assertEqual(launch.call_args.args[0][-1], '/file with spaces.txt')

    def test_rotated_image_still_fits_preview_bounds(self):
        path = self.source / 'rotated.jpg'
        with Image.new('RGB', (400, 200), 'red') as image:
            exif = Image.Exif(); exif[274] = 6
            image.save(path, exif=exif)
        digest, identity, links = app.hash_checked(path)
        _, picture = app.read_preview(app.Entry(str(path), identity, digest, links), 100, 50)
        with picture:
            self.assertLessEqual(picture.width, 100)
            self.assertLessEqual(picture.height, 50)

    def test_long_running_viewer_is_not_reported_as_failed(self):
        import subprocess
        process = Mock()
        process.wait.side_effect = subprocess.TimeoutExpired('viewer', 2)
        with patch.object(app.subprocess, 'Popen', return_value=process):
            app.open_external('/file.txt')

    def test_corrupt_preferences_and_atomic_save(self):
        path = self.root / 'config/settings.json'
        with patch.object(app, 'preferences_path', return_value=path):
            self.assertEqual(app.load_preferences(), {})
            app.save_preferences({'folder': '/hello'})
            self.assertEqual(app.load_preferences()['folder'], '/hello')
            path.write_text('{broken')
            self.assertEqual(app.load_preferences(), {})
            self.assertEqual(len(list(path.parent.iterdir())), 1)


@unittest.skipUnless(os.environ.get('DISPLAY'), 'GUI tests require an X11 display (use xvfb-run)')
class GuiRegressions(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.temp = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp.name)
        for name in ('a.txt', 'b.txt', 'c.txt'):
            (self.root_path / name).write_text('same')
        self.root = tk.Tk()
        self.app = app.App(self.root, persist=False)
        self.app.groups = app.scan(self.root_path)[0]
        self.app.populate()
        self.root.update()

    def tearDown(self):
        self.app.close()
        self.app.preview_thread.join(5)
        self.temp.cleanup()

    def pump(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_new_scan_clears_old_preview(self):
        self.app.tree.selection_set('f0-0')
        self.pump(lambda: 'Loading' not in self.app.text.get('1.0', 'end'))
        generation = self.app.preview_generation
        self.app.folder.set(str(self.root_path)); self.app.minimum.set('0')
        self.app.start_scan()
        self.assertGreater(self.app.preview_generation, generation)
        self.assertEqual(str(self.app.openbutton['state']), 'disabled')
        self.pump(lambda: not self.app.busy)
        self.assertIn('Select a file', self.app.text.get('1.0', 'end'))

    def test_only_one_preview_worker_and_latest_request_wins(self):
        entered, release = threading.Event(), threading.Event()
        original = app.read_preview
        calls = []
        def slow(entry, *args):
            calls.append(entry.path)
            entered.set(); release.wait(3)
            return original(entry, *args)
        with patch.object(app, 'read_preview', slow):
            self.app.tree.selection_set('f0-0'); self.root.update()
            self.assertTrue(entered.wait(2))
            for i in range(30):
                self.app.tree.selection_set(f'f0-{i % 3}'); self.root.update()
            self.app.tree.selection_set('f0-2'); self.root.update()
            release.set()
            self.pump(lambda: 'c.txt' in self.app.text.get('1.0', 'end') and 'Loading' not in self.app.text.get('1.0', 'end'))
        self.assertLessEqual(len(calls), 2)

    def test_small_window_keeps_action_controls_visible(self):
        self.root.geometry('900x640'); self.root.update()
        for widget in (self.app.movebutton, self.app.trashbutton, self.app.exportbutton):
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), self.root.winfo_rooty() + self.root.winfo_height())

    def test_csv_export_has_exact_current_selection(self):
        self.app.select_extras()
        path = self.root_path / 'results.csv'
        with patch('tkinter.filedialog.asksaveasfilename', return_value=str(path)):
            self.app.export_scan()
        text = path.read_text(encoding='utf-8-sig')
        self.assertEqual(text.count(',Remove,'), 2)
        self.assertEqual(text.count(',Keep,'), 1)

    def test_cancel_button_cancels_current_scan(self):
        entered = threading.Event()
        original = app.scan
        def scanning(folder, recursive, minimum, cancel, progress):
            entered.set()
            cancel.wait(3)
            return original(folder, recursive, minimum, cancel, progress)
        self.app.folder.set(str(self.root_path))
        with patch.object(app, 'scan', scanning):
            self.app.start_scan()
            self.assertTrue(entered.wait(2))
            self.app.cancelbutton.invoke()
            try:
                self.assertTrue(self.app.cancel.is_set())
            finally:
                self.app.cancel.set()
                self.pump(lambda: not self.app.busy)
        self.assertIn('Scan cancelled', self.app.status.get())
        self.assertEqual(len(list(self.root_path.iterdir())), 3)

    def test_cancel_button_cancels_current_cleanup(self):
        entered = threading.Event()
        def action(*args):
            cancel = args[-1]
            entered.set()
            cancel.wait(3)
            app.checkpoint(cancel)
        group = self.app.groups[0]
        with patch.object(app, 'act', action):
            self.app.run_actions([(group[0], group, group[1:])], 'move', str(self.root_path))
            self.assertTrue(entered.wait(2))
            self.app.cancelbutton.invoke()
            try:
                self.assertTrue(self.app.cancel.is_set())
            finally:
                self.app.cancel.set()
                self.pump(lambda: not self.app.busy)
        self.assertIn('cancelled', self.app.status.get())
        self.assertTrue(all(Path(e.path).exists() for e in group))
