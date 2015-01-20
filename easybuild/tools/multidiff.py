# #
# Copyright 2014-2015 Ghent University
#
# This file is part of EasyBuild,
# originally created by the HPC team of Ghent University (http://ugent.be/hpc/en),
# with support of Ghent University (http://ugent.be/hpc),
# the Flemish Supercomputer Centre (VSC) (https://vscentrum.be/nl/en),
# the Hercules foundation (http://www.herculesstichting.be/in_English)
# and the Department of Economy, Science and Innovation (EWI) (http://www.ewi-vlaanderen.be/en).
#
# http://github.com/hpcugent/easybuild
#
# EasyBuild is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation v2.
#
# EasyBuild is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with EasyBuild.  If not, see <http://www.gnu.org/licenses/>.
# #
"""
Module which allows the diffing of multiple files

@author: Toon Willems (Ghent University)
@author: Kenneth Hoste (Ghent University)
"""

import difflib
import math
import os
from vsc.utils import fancylogger

from easybuild.tools.filetools import read_file
from easybuild.tools.utilities import det_terminal_size


SEP_WIDTH = 5

# text colors
PURPLE = "\033[0;35m"
# background colors
GREEN_BACK = "\033[0;42m"
RED_BACK = "\033[0;41m"
# end character for colorized text
END_COLOR = "\033[0m"

# meaning characters in diff context
HAT = '^'
MINUS = '-'
PLUS = '+'
SPACE = ' '
QUESTIONMARK = '?'

END_LONG_LINE = '...'

# restrict displaying of differences to limited number of groups
MAX_DIFF_GROUPS = 3


_log = fancylogger.getLogger('multidiff', fname=False)


class MultiDiff(object):
    """
    Class representing a multi-diff.
    """
    def __init__(self, base_fn, base_lines, files, colored=True):
        """
        MultiDiff constructor
        @param base: base to compare with
        @param files: list of files to compare with base
        @param colored: boolean indicating whether a colored multi-diff should be generated
        """
        self.base_fn = base_fn
        self.base_lines = base_lines
        self.files = files
        self.colored = colored
        self.diff_info = {}

    def parse_line(self, line_no, diff_line, meta, squigly_line):
        """
        Register a diff line
        @param line_no: line number
        @param diff_line: diff line generated by difflib
        @param meta: meta information (e.g., filename)
        @param squigly_line: squigly line indicating which characters changed
        """
        # register (diff_line, meta, squigly_line) tuple for specified line number and determined key
        key = diff_line[0]
        if not key in [MINUS, PLUS]:
            _log.error("diff line starts with unexpected character: %s" % diff_line)
        line_key_tuples = self.diff_info.setdefault(line_no, {}).setdefault(key, [])
        line_key_tuples.append((diff_line, meta, squigly_line))

    def color_line(self, line, color):
        """Create colored version of given line, with given color, if color mode is enabled."""
        if self.colored:
            line = ''.join([color, line, END_COLOR])
        return line

    def merge_squigly(self, squigly1, squigly2):
        """Combine two squigly lines into a single squigly line."""
        sq1 = list(squigly1)
        sq2 = list(squigly2)
        # longest line is base
        base, other = (sq1, sq2) if len(sq1) > len(sq2) else (sq2, sq1)

        for i, char in enumerate(other):
            if base[i] in [HAT, SPACE] and base[i] != char:
                base[i] = char

        return ''.join(base)

    def colorize(self, line, squigly):
        """Add colors to the diff line based on the squigly line."""
        if not self.colored:
            return line

        # must be a list so we can insert stuff
        chars = list(line)
        flag = ' '
        offset = 0
        color_map = {
            HAT: GREEN_BACK if line.startswith(PLUS) else RED_BACK,
            MINUS: RED_BACK,
            PLUS: GREEN_BACK,
        }
        if squigly:
            for i, squigly_char in enumerate(squigly):
                if squigly_char != flag:
                    chars.insert(i + offset, END_COLOR)
                    offset += 1
                    if squigly_char in [HAT, MINUS, PLUS]:
                        chars.insert(i + offset, color_map[squigly_char])
                        offset += 1
                    flag = squigly_char
            chars.insert(len(squigly) + offset, END_COLOR)
        else:
            chars.insert(0, color_map.get(line[0], ''))
            chars.append(END_COLOR)

        return ''.join(chars)

    def get_line(self, line_no):
        """
        Return the line information for a specific line
        @param line_no: line number to obtain information for
        @return: list with text lines providing line information
        """
        output = []
        diff_dict = self.diff_info.get(line_no, {})
        for key in [MINUS, PLUS]:
            lines, changes_dict, squigly_dict = set(), {}, {}

            # obtain relevant diff lines
            if key in diff_dict:
                for (diff_line, meta, squigly_line) in diff_dict[key]:
                    if squigly_line:
                        # merge squigly lines
                        if diff_line in squigly_dict:
                            squigly_line = self.merge_squigly(squigly_line, squigly_dict[diff_line])
                        squigly_dict[diff_line] = squigly_line
                    lines.add(diff_line)
                    # track meta info (which filenames are relevant)
                    changes_dict.setdefault(diff_line, set()).add(meta)

            # sort: lines with most changes last, limit number to MAX_DIFF_GROUPS
            lines = sorted(lines, key=lambda line: len(changes_dict[line]))[:MAX_DIFF_GROUPS]

            for diff_line in lines:
                squigly_line = squigly_dict.get(diff_line, '')
                line = ['%s %s' % (line_no, self.colorize(diff_line, squigly_line))]

                # mention to how may files this diff applies
                files = changes_dict[diff_line]
                num_files = len(self.files)
                line.append("(%d/%d)" % (len(files), num_files))

                # list files to which this diff applies (don't list all files)
                if len(files) != num_files:
                    line.append(', '.join(files))

                output.append(' '.join(line))

                # prepend spaces to match line number length in non-color mode
                if not self.colored and squigly_line:
                    prepend = ' ' * (2 + int(math.log10(line_no)))
                    output.append(''.join([prepend, squigly_line]))

        # print seperator only if needed
        if diff_dict and not self.diff_info.get(line_no + 1, {}):
            output.extend([' ', '-' * SEP_WIDTH, ' '])

        return output

    def __str__(self):
        """
        Create a string representation of this multi-diff
        """
        def limit(text, length):
            """Limit text to specified length, terminate color mode and add END_LONG_LINE if trimmed."""
            if len(text) > length:
                maxlen = length - len(END_LONG_LINE)
                res = text[:maxlen]
                if self.colored:
                    res += END_COLOR
                return res + END_LONG_LINE
            else:
                return text

        term_width, _ = det_terminal_size()

        base = self.color_line(self.base_fn, PURPLE)
        filenames = ', '.join(map(os.path.basename, self.files))
        output = [
            "Comparing %s with %s" % (base, filenames),
            '=' * SEP_WIDTH,
        ]

        diff = False
        for i in range(len(self.base_lines)):
            lines = filter(None, self.get_line(i))
            if lines:
                output.append('\n'.join([limit(line, term_width) for line in lines]))
                diff = True

        if not diff:
            output.append("(no diff)")

        output.append('=' * SEP_WIDTH)

        return '\n'.join(output)


def multidiff(base, files, colored=True):
    """
    Generate a diff for multiple files, all compared to base.
    @param base: base to compare with
    @param files: list of files to compare with base
    @param colored: boolean indicating whether a colored multi-diff should be generated
    @return: text with multidiff overview
    """
    differ = difflib.Differ()
    base_lines = read_file(base).split('\n')
    mdiff = MultiDiff(os.path.basename(base), base_lines, files, colored=colored)

    # use the MultiDiff class to store the information
    for filepath in files:
        lines = read_file(filepath).split('\n')
        diff = differ.compare(lines, base_lines)
        filename = os.path.basename(filepath)

        # contruct map of line number to diff lines and mapping between diff lines
        # example partial diff:
        #
        # - toolchain = {'name': 'goolfc', 'version': '2.6.10'}
        # ?                            -               ^   ^
        # 
        # + toolchain = {'name': 'goolf', 'version': '1.6.20'}
        # ?                                           ^   ^
        #
        local_diff = {}
        squigly_dict = {}
        last_added = None
        offset = 1
        for (i, line) in enumerate(diff):
            # diff line indicating changed characters on line above, a.k.a. a 'squigly' line
            if line.startswith(QUESTIONMARK):
                squigly_dict[last_added] = line
                offset -= 1
            # diff line indicating addition change
            elif line.startswith(PLUS):
                local_diff.setdefault(i + offset, []).append((line, filename))
                last_added = line
            # diff line indicated removal change
            elif line.startswith(MINUS):
                local_diff.setdefault(i + offset, []).append((line, filename))
                last_added = line
                offset -= 1

        # construct the multi-diff based on the constructed dict
        for line_no in local_diff:
            for (line, filename) in local_diff[line_no]:
                mdiff.parse_line(line_no, line.rstrip(), filename, squigly_dict.get(line, '').rstrip())

    return str(mdiff)
