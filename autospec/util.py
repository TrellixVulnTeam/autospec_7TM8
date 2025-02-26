#!/bin/true
#
# util.py - part of autospec
# Copyright (C) 2015 Intel Corporation
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import hashlib
import os
import re
import shlex
import subprocess
import sys

dictionary_filename = os.path.dirname(__file__) + "/translate.dic"
dictionary = [line.strip() for line in open(dictionary_filename, 'r')]
os_paths = None
debugging : bool = False


def call_fast(command, cwd=None, check=True):
    """Subprocess.call fast convenience wrapper."""
    returncode = 1

    full_args = {
        "args": shlex.split(command),
        "universal_newlines": True,
        "cwd": cwd,
    }

    returncode = subprocess.call(**full_args)
    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, full_args["args"], None)

    return returncode


def scantree(path):
    """Recursively yield DirEntry objects for given directory."""
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scantree(entry.path)
        else:
            yield entry


def call(command, logfile=None, check=True, **kwargs):
    """Subprocess.call convenience wrapper."""
    returncode = 1

    full_args = {
        "args": shlex.split(command),
        "universal_newlines": True,
    }

    full_args.update(kwargs)

    if logfile:
        full_args["stdout"] = open(logfile, "w")
        full_args["stderr"] = subprocess.STDOUT
        returncode = subprocess.call(**full_args)
        full_args["stdout"].close()
    else:
        returncode = subprocess.call(**full_args)

    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, full_args["args"], None)

    return returncode


def _file_write(self, s):
    s = s.strip()
    if not s.endswith("\n"):
        s += "\n"
    self.write(s)


def translate(package):
    """Convert terms to their alternate definition."""
    global dictionary
    for item in dictionary:
        if item.startswith(package + "="):
            return item.split("=")[1]
    return package


def do_regex(patterns, re_str):
    """Find a match in multiple patterns."""
    for p in patterns:
        match = re.search(p, re_str)
        if match:
            return match


def get_contents(filename):
    """Get contents of filename."""
    with open(filename, "rb") as f:
        return f.read()
    return None


def get_sha1sum(filename):
    """Get sha1 sum of filename."""
    sh = hashlib.sha1()
    sh.update(get_contents(filename))
    return sh.hexdigest()


def _supports_color():
    # FIXME: check terminfo instead
    return sys.stdout.isatty()


def _print_message(message, level, color=None):
    prefix = level
    if color and _supports_color():
        # FIXME: use terminfo instead
        if color == 'red':
            params = '31;1'
        elif color == 'green':
            params = '32;1'
        elif color == 'yellow':
            params = '33;1'
        elif color == 'blue':
            params = '34;1'
        prefix = f'\033[{params}m{level}\033[0m'
    print(f'[{prefix}] {message}')


def _print_message_extra(message, level, color=None, color_text=None):
    prefix = level
    if color and _supports_color():
        # FIXME: use terminfo instead
        if color == 'red':
            params = '31;1'
        elif color == 'green':
            params = '32;1'
        elif color == 'yellow':
            params = '33;1'
        elif color == 'blue':
            params = '34;1'
        prefix = f'\033[{params}m{level}\033[0m'
    if color_text and _supports_color():
        # FIXME: use terminfo instead
        if color_text == 'red':
            params2 = '31;1'
        elif color_text == 'green':
            params2 = '32;1'
        elif color_text == 'yellow':
            params2 = '33;1'
        elif color_text == 'blue':
            params2 = '34;1'
        elif color_text == 'orange':
            params2 = '38;5;208'
        message_colored = f'\033[{params2}m{message}\033[0m'
    print(f'[{prefix}] {message_colored}')


def print_error(message):
    """Print error, color coded for TTYs."""
    _print_message(message, 'ERROR', 'red')


def print_fatal(message):
    """Print fatal error, color coded for TTYs."""
    _print_message(message, 'FATAL', 'red')


def print_warning(message):
    """Print warning, color coded for TTYs."""
    _print_message(message, 'WARNING', 'red')


def print_extra_warning(message):
    """Print warning, color coded for TTYs."""
    _print_message_extra(message, 'WARNING', 'red', 'orange')


def print_info(message):
    """Print informational message, color coded for TTYs."""
    _print_message(message, 'INFO', 'yellow')


def print_success(message):
    """Print success message, color coded for TTYs."""
    _print_message(message, 'SUCCESS', 'green')


def print_debug(message):
    """Print debug messages, color coded for TTYs."""
    _print_message(message, 'DEBUG', 'red')


def binary_in_path(binary):
    """Determine if the given binary exists in the provided filesystem paths."""
    global os_paths
    if not os_paths:
        os_paths = os.getenv("PATH", default="/usr/bin:/bin").split(os.pathsep)

    for path in os_paths:
        if os.path.exists(os.path.join(path, binary)):
            return True
    return False


def write_out(filename, content, mode="w"):
    """File.write convenience wrapper."""
    with open_auto(filename, mode) as require_f:
        require_f.write(content)


def open_auto(*args, **kwargs):
    """Open a file with UTF-8 encoding.

    Open file with UTF-8 encoding and "surrogate" escape characters that are
    not valid UTF-8 to avoid data corruption.
    """
    # 'encoding' and 'errors' are fourth and fifth positional arguments, so
    # restrict the args tuple to (file, mode, buffering) at most
    assert len(args) <= 3
    assert 'encoding' not in kwargs
    assert 'errors' not in kwargs
    return open(*args, encoding="utf-8", errors="surrogateescape", **kwargs)
