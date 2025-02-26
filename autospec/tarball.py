#!/usr/bin/true
#
# tarball.py - part of autospec
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

import configparser
import os
import re
import tarfile
import zipfile
import util
from collections import OrderedDict

import download
from util import do_regex, get_sha1sum, print_fatal, write_out, print_debug


class Source(object):
    """Holds data and methods for source code or archives management."""

    def __init__(self, url, destination, path, pattern=None):
        """Set default values for source file."""
        self.url = url
        self.destination = destination
        self.path = path
        self.pattern = pattern
        self.type = None
        self.prefix = None
        self.subdir = None
        self.gem_subdir = None

        # Extra  compressed archives
        if not self.destination.startswith(':'):
            self.set_type()
            self.set_prefix()

    def set_type(self):
        """Determine compression type."""
        if self.url.lower().endswith(('.zip', 'jar')):
            self.type = 'zip'
        elif self.url.lower().endswith('list'):
            self.type = 'go'
        else:
            self.type = 'tar'

    def set_prefix(self):
        """Determine the prefix and subdir if no prefix."""
        prefix_method = getattr(self, 'set_{}_prefix'.format(self.type))
        prefix_method()

        # When there is no prefix, create subdir
        if not self.prefix and not self.pattern == "ruby":
            self.subdir = os.path.splitext(os.path.basename(self.path))[0]
        if not self.prefix and self.pattern == "ruby":
            self.subdir = os.path.splitext(os.path.basename(self.path))[0]
            self.gem_subdir = os.path.splitext(os.path.basename(self.path))[0]

    def set_tar_prefix(self):
        """Determine prefix folder name of tar file."""
        if tarfile.is_tarfile(self.path):
            with tarfile.open(self.path, 'r') as content:
                lines = content.getnames()
                # When tarball is not empty
                if len(lines) == 0:
                    print_fatal("Tar file doesn't appear to have any content")
                    exit(1)
                elif len(lines) > 1:
                    if 'package.xml' in lines and self.pattern in ['phpize']:
                        lines.remove('package.xml')
                    self.prefix = os.path.commonpath(lines)
        else:
            print_fatal("Not a valid tar file.")
            exit(1)

    def set_zip_prefix(self):
        """Determine prefix folder name of zip file."""
        if zipfile.is_zipfile(self.path):
            with zipfile.ZipFile(self.path, 'r') as content:
                lines = content.namelist()
                # When zipfile is not empty
                if len(lines) > 0:
                    self.prefix = os.path.commonpath(lines)
                else:
                    print_fatal("Zip file doesn't appear to have any content")
                    exit(1)
        else:
            print_fatal("Not a valid zip file.")
            exit(1)

    def set_go_prefix(self):
        """Set empty prefix for go packages (*.list)."""
        self.prefix = ''

    def extract(self, base_path):
        """Prepare extraction path and call specific extraction method."""
        if not self.prefix:
            extraction_path = os.path.join(base_path, self.subdir)
        else:
            extraction_path = base_path

        extract_method = getattr(self, 'extract_{}'.format(self.type))
        extract_method(extraction_path)

    def extract_tar(self, extraction_path):
        """Extract tar in path."""
        with tarfile.open(self.path) as content:
            def is_within_directory(directory, target):
                
                abs_directory = os.path.abspath(directory)
                abs_target = os.path.abspath(target)
            
                prefix = os.path.commonprefix([abs_directory, abs_target])
                
                return prefix == abs_directory
            
            def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
            
                for member in tar.getmembers():
                    member_path = os.path.join(path, member.name)
                    if not is_within_directory(path, member_path):
                        raise Exception("Attempted Path Traversal in Tar File")
            
                tar.extractall(path, members, numeric_owner=numeric_owner) 
                
            
            safe_extract(content, path=extraction_path)

    def extract_zip(self, extraction_path):
        """Extract zip in path."""
        with zipfile.ZipFile(self.path, 'r') as content:
            content.extractall(path=extraction_path)

    def extract_go(self, extraction_path):
        """Pretend to do something."""
        return


def convert_version(ver_str, name):
    """Remove disallowed characters from the version."""
    # banned substrings. It is better to remove these here instead of filtering
    # them out with expensive regular expressions
    banned_subs = ["x86.64", "source", "src", "all", "bin", "release", "rh",
                   "ga", ".ce", "lcms", "onig", "linux", "gc", "sdk", "orig",
                   "jurko", "%2f", "%2F", "%20"]

    # package names may be modified in the version string by adding "lib" for
    # example. Remove these from the name before trying to remove the name from
    # the version
    name_mods = ["lib", "core", "pom", "opa-"]

    # enforce lower-case strings to make them easier to standardize
    ver_str = ver_str.lower()
    # remove the package name from the version string
    ver_str = ver_str.replace(name.lower(), '')
    # handle modified name substrings in the version string
    for mod in name_mods:
        ver_str = ver_str.replace(name.replace(mod, ""), "")

    # replace illegal characters
    ver_str = ver_str.strip().replace('-', '.').replace('_', '.')

    # remove banned substrings
    for sub in banned_subs:
        ver_str = ver_str.replace(sub, "")

    # remove consecutive '.' characters
    while ".." in ver_str:
        ver_str = ver_str.replace("..", ".")

    return ver_str.strip(".")


class Content(object):
    """Detect static information about the project."""

    def __init__(self, url, name, version, archives, config, base_path, giturl, download_from_git, branch, new_archives_from_git, force_module, force_fullclone):
        """Initialize Default content settings."""
        self.name = name
        self.rawname = ""
        self.version = version
        self.multi_version = OrderedDict()
        self.release = "1"
        self.url = url
        self.path = ""
        self.tarball_prefix = ""
        self.gcov_file = ""
        self.archives = archives
        self.giturl = giturl
        self.repo = ""
        self.domain = ""
        self.prefixes = dict()
        self.config = config
        self.base_path = base_path
        self.download_from_git = download_from_git
        self.branch = branch
        self.force_module = force_module
        self.force_fullclone = force_fullclone
        self.archives_from_git = new_archives_from_git
        self.gem_subdir = str()

    def write_upstream(self, sha, tarfile, mode="w"):
        """Write the upstream hash to the upstream file."""
        write_out(os.path.join(self.config.download_path, "upstream"),
                  os.path.join(sha, tarfile) + "\n", mode=mode)

    def extract_sources(self, main_src, archives_src):
        """Extract sources."""
        full_list_src = [main_src] + archives_src
        for src in full_list_src:
            if src.destination != ':':
                src.extract(self.base_path)

    def check_or_get_file(self, upstream_url, tarfile, mode="w"):
        """Download tarball from url unless it is present locally."""
        tarball_path = self.config.download_path + "/" + tarfile
        if not os.path.isfile(tarball_path):
            download.do_curl(upstream_url, dest=tarball_path, is_fatal=True)
            self.write_upstream(get_sha1sum(tarball_path), tarfile, mode)
        else:
            self.write_upstream(get_sha1sum(tarball_path), tarfile, mode)
        return tarball_path

    def process_main_source(self, url):
        """Download and get important information from main source code."""
        src_path = self.check_or_get_file(url, os.path.basename(url))
        main_src = Source(url, '', src_path, self.config.default_pattern)
        return main_src

    def print_header(self):
        """Print header for autospec run."""
        print("Processing", self.url)
        print("=" * 105)
        print("Name        :", self.name)
        print("Version     :", self.version)
        print("Prefix      :", self.tarball_prefix)

    def set_giturl_and_domain(self):
        """Set giturl and domain from the config (needs config refactor)."""
        options_path = os.path.join(self.config.download_path, 'options.conf')
        if os.path.exists(options_path):
            config_f = configparser.ConfigParser(interpolation=None)
            config_f.read(options_path)
            if "package" in config_f.sections():
                if "giturl" in config_f["package"]:
                    self.giturl = config_f["package"].get("giturl")
                if "domain" in config_f["package"]:
                    self.domain = config_f["package"].get("domain")

    def set_multi_version(self, ver):
        """Add ver to multi_version set and return latest version."""
        self.multi_version = self.config.parse_config_versions()
        if ver:
            # Some build patterns put multiple versions in the same package.
            # For those patterns add to the multi_version list
            if self.config.default_pattern in ["godep"]:
                self.multi_version[ver] = ""
            else:
                self.multi_version = {ver: ""}
        elif not self.multi_version:
            # Fall back to ensure a version is always set
            # (otherwise the last known version will be used)
            self.multi_version = {"1": ""}
        latest = sorted(self.multi_version.keys())[-1]

        return latest

    def name_and_version(self, filemanager):
        """Parse the url for the package name and version."""
        tarfile = os.path.basename(self.url)

        # If both name and version overrides are set via commandline, set the name
        # and version variables to the overrides and bail. If only one override is
        # set, continue to auto detect both name and version since the URL parsing
        # handles both. In this case, wait until the end to perform the override of
        # the one that was set. An extra conditional, that version_arg is a string
        # is added to enable a package to have multiple versions at the same time
        # for some language ecosystems.
        if self.name and self.version:
            # rawname == name in this case
            self.rawname = self.name
            self.version = convert_version(self.set_multi_version(self.version), self.name)
            return

        name = self.name
        self.rawname = self.name
        version = ""
        # it is important for the more specific patterns to come first
        pattern_options = [
            # handle font packages with names ending in -nnndpi
            r"(.*-[0-9]+dpi)[-_]([0-9]+[a-zA-Z0-9\+_\.\-\~]*)\.(tgz|tar|zip)",
            r"(.*?)[-_][vs]?([0-9]+[a-zA-Z0-9\+_\.\-\~]*)\.(tgz|tar|zip)",
        ]
        match = do_regex(pattern_options, tarfile)
        if match:
            name = match.group(1).strip()
            version = convert_version(match.group(2), name)

        # R package
        if "cran.r-project.org" in self.url or "cran.rstudio.com" in self.url and name:
            filemanager.want_dev_split = False
            self.rawname = name
            name = "R-" + name

        if ".cpan.org/" in self.url or ".metacpan.org/" in self.url and name:
            name = "perl-" + name

        if "github.com" in self.url:
            # define regex accepted for valid packages, important for specific
            # patterns to come before general ones
            github_patterns = [r"https?://github.com/(.*)/(.*?)/archive/refs/tags/[vVrR]?(.*)\.tar",
                               r"https?://github.com/(.*)/(.*?)/archive/[v|r]?.*/(.*).tar",
                               r"https?://github.com/(.*)/(.*?)/archive/[-a-zA-Z_]*-(.*).tar",
                               r"https?://github.com/(.*)/(.*?)/archive/[vVrR]?(.*).tar",
                               r"https?://github.com/(.*)/.*-downloads/releases/download/.*?/(.*)-(.*).tar",
                               r"https?://github.com/(.*)/(.*?)/releases/download/(.*)/",
                               r"https?://github.com/(.*)/(.*?)/files/.*?/(.*).tar"]

            match = do_regex(github_patterns, self.url)
            if match:
                self.repo = match.group(2).strip()
                if self.repo not in name:
                    # Only take the repo name as the package name if it's more descriptive
                    name = self.repo
                elif name != self.repo:
                    name = re.sub(r"release-", '', name)
                    name = re.sub(r"\d*$", '', name)
                self.rawname = name
                version = match.group(3).replace(name, '')
                if "/archive/" not in self.url:
                    version = re.sub(r"^[-_.a-zA-Z]+", "", version)
                version = convert_version(version, name)
                if not self.giturl:
                    self.giturl = "https://github.com/" + match.group(1).strip() + "/" + self.repo + ".git"

        # SQLite tarballs use 7 digit versions, e.g 3290000 = 3.29.0, 3081002 = 3.8.10.2
        if "sqlite.org" in self.url:
            major = version[0]
            minor = version[1:3].lstrip("0").zfill(1)
            patch = version[3:5].lstrip("0").zfill(1)
            build = version[5:7].lstrip("0")
            version = major + "." + minor + "." + patch + "." + build
            version = version.strip(".")

        # Construct gitlab giturl for GNOME projects, and update previous giturls
        # that pointed to the GitHub mirror.
        if "download.gnome.org" in self.url:
            if not self.giturl or "github.com/GNOME" in self.giturl or "git.gnome.org" in self.giturl:
                self.giturl = "https://gitlab.gnome.org/GNOME/{}".format(name)

        if "mirrors.kernel.org" in self.url:
            m = re.search(r".*/sourceware/(.*?)/releases/(.*?).tgz", self.url)
            if m:
                name = m.group(1).strip()
                version = convert_version(m.group(2), name)

        if "sourceforge.net" in self.url:
            scf_pats = [r"projects/.*/files/(.*?)/(.*?)/[^-]*(-src)?.tar.gz",
                        r"downloads.sourceforge.net/.*/([a-zA-Z]+)([-0-9\.]*)(-src)?.tar.gz"]
            match = do_regex(scf_pats, self.url)
            if match:
                name = match.group(1).strip()
                version = convert_version(match.group(2), name)

        if "bitbucket.org" in self.url:
            bitbucket_pats = [r"/.*/(.*?)/.*/.*v([-\.0-9a-zA-Z_]*?).(tar|zip)",
                              r"/.*/(.*?)/.*/([-\.0-9a-zA-Z_]*?).(tar|zip)"]

            match = do_regex(bitbucket_pats, self.url)
            if match:
                name = match.group(1).strip()
                version = convert_version(match.group(2), name)

        # ruby
        if "rubygems.org/" in self.url:
            m = re.search(r"(.*?)[\-_](v*[0-9]+[a-zA-Z0-9\+_\.\-\~]*)\.gem", tarfile)
            if m:
                name = "rubygem-" + m.group(1).strip()
                # remove release candidate tag from the package name
                # https://rubygems.org/downloads/ruby-rc4-0.1.5.gem
                b = name.find("-rc")
                if b > 0:
                    name = name[:b]
                self.rawname = m.group(1).strip()
                version = convert_version(m.group(2), name)

        # rust crate
        if "crates.io" in self.url:
            m = re.search(r"/crates.io/api/v[0-9]+/crates/(.*)/(.*)/download.*\.crate", self.url)
            if m:
                name = m.group(1).strip()
                version = convert_version(m.group(2), name)

        if "gitlab.com" in self.url:
            # https://gitlab.com/leanlabsio/kanban/-/archive/1.7.1/kanban-1.7.1.tar.gz
            m = re.search(r"gitlab\.com/.*/(.*)/-/archive/(?:VERSION_|[vVrR])?(.*)/", self.url)
            if m:
                name = m.group(1).strip()
                version = convert_version(m.group(2), name)

        if "git.sr.ht" in self.url:
            # https://git.sr.ht/~sircmpwn/scdoc/archive/1.9.4.tar.gz
            m = re.search(r"git\.sr\.ht/.*/(.*)/archive/(.*).tar.gz", self.url)
            if m:
                name = m.group(1).strip()
                version = convert_version(m.group(2), name)

        # override name and version from commandline
        self.name = self.name if self.name else name
        self.version = self.version if self.version else version
        self.version = self.set_multi_version(self.version)

    def set_gcov(self):
        """Set the gcov file name."""
        gcov_path = os.path.join(self.config.download_path, self.name + ".gcov")
        if os.path.isfile(gcov_path):
            self.gcov_file = self.name + ".gcov"

    def process_go_archives(self, go_archives):
        """Set up extra archives required by go packages."""
        base_url = os.path.dirname(self.url)
        for ver in self.multi_version:
            url_info = os.path.join(base_url, f"{ver}.info")
            url_mod = os.path.join(base_url, f"{ver}.mod")
            url_zip = os.path.join(base_url, f"{ver}.zip")
            # Append elements in pairs url and destination if doesn't exist
            if url_info not in self.archives:
                go_archives.extend([url_info, ':'])
            if url_mod not in self.archives:
                go_archives.extend([url_mod, ':'])
            if url_zip not in self.archives:
                go_archives.extend([url_zip, ''])
            self.config.sources["godep"] += [url_info, url_mod, url_zip]

    def process_multiver_archives(self, main_src, multiver_archives):
        """Set up multiversion archives."""
        config_versions = self.config.parse_config_versions()
        # Check if exist more than one version.
        if len(config_versions) > 1:
            for extraver in config_versions:
                extraurl = config_versions[extraver]
                if extraurl and extraurl != main_src.url:
                    self.config.sources["version"].append(extraurl)
                    multiver_archives.append(extraurl)
                    multiver_archives.append('')
                    self.set_multi_version(None)

    def process_archives(self, main_src):
        """Process extra sources needed by package.

        This sources include: archives, go archives and multiversion.
        """
        go_archives = []
        multiver_archives = []
        src_objects = []

        if os.path.basename(main_src.url) == "list":
            # Add extra archives and multiversion for Go packages
            self.process_go_archives(go_archives)
        else:
            # Add multiversion for the rest of the patterns
            self.process_multiver_archives(main_src, multiver_archives)

        full_archives = self.archives + go_archives + multiver_archives
        # Download and extract full list
        for arch_url, destination in zip(full_archives[::2], full_archives[1::2]):
            #if util.debugging:
                #print_debug("arch_url 3: {} - {}".format(arch_url, destination))
            src_path = self.check_or_get_file(arch_url, os.path.basename(arch_url), mode="a")
            # Create source object and extract archive
            archive = Source(arch_url, destination, src_path, self.config.default_pattern)
            # Add archive prefix to list
            self.config.archive_details[arch_url + "prefix"] = archive.prefix
            self.prefixes[arch_url] = archive.prefix
            # Add archive to list
            src_objects.append(archive)

        return src_objects

    def process(self, filemanager):
        """Download and process the tarball."""
        # determine build pattern and build requirements from url
        self.set_giturl_and_domain()
        # determine name and version of package
        self.name_and_version(filemanager)
        # Store the top-level version
        self.config.versions[self.version] = self.url
        # set gcov file information, must be done after name is set since the gcov
        # name is created by adding ".gcov" to the package name (if a gcov file
        # exists)
        self.set_gcov()
        # Download and process main source
        main_src = self.process_main_source(self.url)
        # Store the detected prefix associated with this file
        self.prefixes[self.url] = main_src.prefix
        self.tarball_prefix = main_src.prefix
        if self.config.default_pattern == "ruby":
            self.gem_subdir = main_src.gem_subdir
            #print(f"self.gem_subdir: {self.gem_subdir}")
        # set global path with tarball_prefix
        self.path = os.path.join(self.base_path, self.tarball_prefix)
        #if util.debugging:
            #print_debug(f"tarball.py - self.url: {self.url}")
            #print_debug(f"tarball.py - self.path: {self.path}")
            #print_debug(f"tarball.py - self.base_path: {self.base_path}")
            #print_debug(f"tarball.py - self.tarball_prefix: {self.tarball_prefix}")
        # Now that the metadata has been collected print the header
        self.print_header()
        # Download and process extra sources: archives, go archives and
        # multiversion
        archives_src = self.process_archives(main_src)
        # Extract all sources
        self.extract_sources(main_src, archives_src)
