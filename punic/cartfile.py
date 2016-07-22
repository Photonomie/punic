from __future__ import division, absolute_import, print_function

__all__ = ['Cartfile']

import re
from pathlib2 import Path
from .basic_types import *
from .errors import *


class Cartfile(object):
    def __init__(self, specifications=None, overrides=None):
        self.specifications = specifications if specifications else []
        self.overrides = overrides

    def read(self, source):
        # type: (Path)

        if isinstance(source, Path):
            if not source.exists():
                raise CartfileNotFound(path=source)
            source = source.open().read()

        # TODO: This is of course super feeble parsing. URLs with #s in them can break for example
        lines = [line.rstrip() for line in source.splitlines()]
        lines = [line for line in lines if not line.startswith('#')]  # NB: we strip out comment lines
        lines = [re.sub(r'#.+', '', line) for line in lines]
        lines = [line.strip() for line in lines]
        lines = [line for line in lines if line]
        self.specifications = [Specification.cartfile_string(line, self.overrides) for line in lines]

    def write(self, destination):
        # type: (File)
        strings = [str(specification) for specification in self.specifications]
        string = u'\n'.join(sorted(strings)) + '\n'
        destination.write(string)
