#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/output_service.py のテスト(画面を起動せずに実行できる)

SerialController フォルダで実行する:
    python -m unittest discover -s tests
"""
from __future__ import annotations

import io
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import output_service  # noqa: E402
from services.output_service import OutputService, OutputUpdate  # noqa: E402


class OutputServiceTest(unittest.TestCase):
    def test_appends_are_joined_per_area(self):
        service = OutputService()
        service.channel(1).enqueue("a", "one\n")
        service.channel(2).enqueue("a", "other\n")
        service.channel(1).enqueue("a", "two\n")
        self.assertEqual(
            service.drain(lambda: 0),
            [OutputUpdate(1, 0, False, "one\ntwo\n"), OutputUpdate(2, 0, False, "other\n")],
        )
        self.assertEqual(service.drain(lambda: 0), [])

    def test_overwrite_discards_earlier_text(self):
        service = OutputService()
        service.enqueue(1, "a", "old\n")
        service.enqueue(1, "w", "new\n")
        service.enqueue(1, "a", "more\n")
        self.assertEqual(service.drain(lambda: 0), [OutputUpdate(1, 0, True, "new\nmore\n")])

    def test_delete_clears_without_text(self):
        service = OutputService()
        service.enqueue(2, "a", "old\n")
        service.enqueue(2, "d", "ignored")
        self.assertEqual(service.drain(lambda: 0), [OutputUpdate(2, 0, True, "")])

    def test_page_is_decided_when_written(self):
        pages = [2]
        service = OutputService(get_page=lambda: pages[0])
        service.enqueue(1, "a", "to page 2\n")
        pages[0] = 1
        service.enqueue(1, "a", "to page 1\n")
        self.assertEqual(
            service.drain(lambda: 0),
            [OutputUpdate(1, 2, False, "to page 2\n"), OutputUpdate(1, 1, False, "to page 1\n")],
        )

    def test_undecided_page_goes_to_the_active_page(self):
        service = OutputService()
        service.enqueue(1, "a", "text\n")
        self.assertEqual(service.drain(lambda: 2), [OutputUpdate(1, 2, False, "text\n")])

    def test_active_page_is_not_asked_when_nothing_needs_it(self):
        def fail():
            raise AssertionError("表示中のページは調べない")

        service = OutputService(get_page=lambda: 1)
        self.assertEqual(service.drain(fail), [])
        service.enqueue(1, "a", "text\n")
        self.assertEqual(service.drain(fail), [OutputUpdate(1, 1, False, "text\n")])

    def test_text_over_the_limit_keeps_only_the_tail(self):
        service = OutputService(max_lines=3)
        service.enqueue(1, "a", "".join(f"line {i}\n" for i in range(10)))
        self.assertEqual(service.drain(lambda: 0), [OutputUpdate(1, 0, True, "line 7\nline 8\nline 9\n")])

    def test_text_within_the_limit_is_kept(self):
        service = OutputService(max_lines=3)
        service.enqueue(1, "a", "a\nb\nc\n")
        self.assertEqual(service.drain(lambda: 0), [OutputUpdate(1, 0, False, "a\nb\nc\n")])

    def test_writes_from_threads_are_all_received(self):
        service = OutputService()
        threads = [
            threading.Thread(target=lambda n=n: [service.enqueue(1, "a", f"{n}\n") for _ in range(200)]) for n in range(5)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        (update,) = service.drain(lambda: 0)
        self.assertEqual(update.text.count("\n"), 1000)

    def test_redirect_stdout(self):
        service = OutputService()
        original = sys.stdout
        try:
            service.redirect_stdout(2)
            print("hello")
            sys.stdout.flush()
        finally:
            sys.stdout = original
        self.assertEqual(service.drain(lambda: 0), [OutputUpdate(2, 0, False, "hello\n")])

    def test_module_does_not_import_tkinter(self):
        with io.open(output_service.__file__, encoding="utf-8") as file:
            source = file.read()
        self.assertNotIn("import tkinter", source)
        self.assertNotIn("from tkinter", source)


if __name__ == "__main__":
    unittest.main()
