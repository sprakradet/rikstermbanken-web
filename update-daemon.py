#!/usr/bin/python3

import os
import sys
import time
import threading
import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess

logfile = open("/var/www/rikstermbanken/update-bankvalvet.log", "at")
rootdir = "/var/www/rikstermbanken/bankvalvet"
event_file = "/var/www/rikstermbanken/daemoncontrol/update"


change_event = threading.Event()

class Handler(FileSystemEventHandler):
    @staticmethod
    def on_modified(event):
        if event.is_directory:
            return
        change_event.set()

def print_stream(stream, name, f):
    for row in stream.decode("utf-8").splitlines():
        print(name, row.rstrip("\n"), file=f)

def run_import():
    now = datetime.datetime.now()
    print("===================", file=logfile)
    print(now.strftime("%Y-%m-%d %H:%M:%S"), file=logfile)
    print("===================", file=logfile)
    logfile.flush()

    git_pull = subprocess.run(["git", "-C", rootdir, "pull"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print_stream(git_pull.stdout, "[git pull stdout]", logfile)
    print_stream(git_pull.stderr, "[git pull stderr]", logfile)
    git_pull.check_returncode()
    logfile.flush()

    import_bankvalvet = subprocess.run([
        "/usr/bin/python3",
        "/var/www/rikstermbanken/src/import_bankvalvet.py",
        rootdir
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print_stream(import_bankvalvet.stdout, "[import_bankvalvet stdout]", logfile)
    print_stream(import_bankvalvet.stderr, "[import_bankvalvet stderr]", logfile)
    import_bankvalvet.check_returncode()
    print("", file=logfile)
    logfile.flush()

while True:
    event_handler = Handler()
    observer = Observer()
    observer.schedule(event_handler, event_file)
    observer.start()
    try:
        while True:
            # Always run import first
            run_import()

            # Wait for update event or 15 minutes
            change_event.wait(60*15)
            change_event.clear()
    finally:
        observer.stop()
        observer.join()
