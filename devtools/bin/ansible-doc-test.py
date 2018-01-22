#!/usr/bin/python

# (c) 2012, Jan-Piet Mens <jpmens () gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import sys
import optparse


import textwrap
import re
import optparse
import datetime
import fcntl
import termios
import struct

from ansible import utils
from ansible.utils import module_docs
import ansible.constants as C
from ansible.utils import version
import traceback

MODULEDIR = C.DEFAULT_MODULE_PATH

_ITALIC = re.compile(r"I\(([^)]+)\)")
_BOLD   = re.compile(r"B\(([^)]+)\)")
_MODULE = re.compile(r"M\(([^)]+)\)")
_URL    = re.compile(r"U\(([^)]+)\)")
_CONST  = re.compile(r"C\(([^)]+)\)")

BLACKLIST_EXTS = ('.pyc', '.swp', '.bak', '~', '.rpm')
IGNORE_FILES = [ "COPYING", "CONTRIBUTING", "LICENSE", "README", "VERSION"]

def tty_ify(text):
    t = _ITALIC.sub("`" + r"\1" + "'", text)    # I(word) => `word'
    t = _BOLD.sub("*" + r"\1" + "*", t)         # B(word) => *word*
    t = _MODULE.sub("[" + r"\1" + "]", t)       # M(word) => [word]
    t = _URL.sub(r"\1", t)                      # U(word) => word
    t = _CONST.sub("`" + r"\1" + "'", t)        # C(word) => `word'

    return t

def get_man_text(doc):
    opt_indent="        "
    text = []
    text.append("> %s\n" % doc['module'].upper())

    desc = " ".join(doc['description'])

    text.append("%s\n" % textwrap.fill(tty_ify(desc), initial_indent="  ", subsequent_indent="  "))

    if 'option_keys' in doc and len(doc['option_keys']) > 0:
        text.append("Options (= is mandatory):\n")

    for o in sorted(doc['option_keys']):
        opt = doc['options'][o]

        if opt.get('required', False):
            opt_leadin = "="
        else:
            opt_leadin = "-"

        text.append("%s %s" % (opt_leadin, o))

        desc = " ".join(opt['description'])

        if 'choices' in opt:
            choices = ", ".join(str(i) for i in opt['choices'])
            desc = desc + " (Choices: " + choices + ")"
        if 'default' in opt:
            default = str(opt['default'])
            desc = desc + " [Default: " + default + "]"
        text.append("%s\n" % textwrap.fill(tty_ify(desc), initial_indent=opt_indent,
                             subsequent_indent=opt_indent))

    if 'notes' in doc and len(doc['notes']) > 0:
        notes = " ".join(doc['notes'])
        text.append("Notes:%s\n" % textwrap.fill(tty_ify(notes), initial_indent="  ",
                            subsequent_indent=opt_indent))


    if 'requirements' in doc and doc['requirements'] is not None and len(doc['requirements']) > 0:
        req = ", ".join(doc['requirements'])
        text.append("Requirements:%s\n" % textwrap.fill(tty_ify(req), initial_indent="  ",
                            subsequent_indent=opt_indent))

    if 'examples' in doc and len(doc['examples']) > 0:
        text.append("Example%s:\n" % ('' if len(doc['examples']) < 2 else 's'))
        for ex in doc['examples']:
            text.append("%s\n" % (ex['code']))

    if 'plainexamples' in doc and doc['plainexamples'] is not None:
        text.append("EXAMPLES:")
        text.append(doc['plainexamples'])
    if 'returndocs' in doc and doc['returndocs'] is not None:
        text.append("RETURN VALUES:")
        text.append(doc['returndocs'])
    text.append('')

    return "\n".join(text)

def main():
    p = optparse.OptionParser(
        version=version("%prog"),
        usage='usage: %prog [options] [module...]',
        description='Show Ansible module documentation',
    )

    p.add_option("-M", "--module-path",
            action="store",
            dest="module_path",
            default=MODULEDIR,
            help="Ansible modules/ directory")
    p.add_option('-v', action='version', help='Show version number and exit')

    (options, args) = p.parse_args()

    if options.module_path is not None:
        for i in options.module_path.split(os.pathsep):
            utils.plugins.module_finder.add_directory(i)

    def print_paths(finder):
        ''' Returns a string suitable for printing of the search path '''

        # Uses a list to get the order right
        ret = []
        for i in finder._get_paths():
            if i not in ret:
                ret.append(i)
        return os.pathsep.join(ret)

    has_error = False
    for module in args:
        filename = utils.plugins.module_finder.find_plugin(module)
        if filename is None:
            sys.stderr.write("module %s not found in %s\n" % (module, print_paths(utils.plugins.module_finder)))
            continue

        if any(filename.endswith(x) for x in BLACKLIST_EXTS):
            continue

        try:
            doc, plainexamples, returndocs = module_docs.get_docstring(filename)
        except:
            traceback.print_exc()
            sys.stderr.write("ERROR: module %s has a documentation error formatting or is missing documentation\n" % module)
            has_error = True
            continue

        if doc is None:
            # this typically means we couldn't even parse the docstring, not just that the YAML is busted,
            # probably a quoting issue.
            sys.stderr.write("ERROR: module %s missing documentation (or could not parse documentation)\n" % module)
            has_error = True
        else:
            all_keys = []
            for (k,v) in doc['options'].iteritems():
                all_keys.append(k)
            all_keys = sorted(all_keys)
            doc['option_keys'] = all_keys

            doc['filename']         = filename
            doc['docuri']           = doc['module'].replace('_', '-')
            doc['now_date']         = datetime.date.today().strftime('%Y-%m-%d')
            doc['plainexamples']    = plainexamples
            doc['returndocs']       = returndocs

            text = get_man_text(doc)
            try:
                text.decode('ascii')
            except (UnicodeDecodeError, UnicodeEncodeError):
                traceback.print_exc()
                sys.stderr.write("ERROR: module %s has an documentation encoding error\n" % module)
                has_error = True

    if has_error:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()
