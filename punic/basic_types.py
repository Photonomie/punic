from __future__ import division, absolute_import, print_function

import re
import functools
from pathlib2 import Path
from memoize import mproperty
from flufl.enum import Enum
import six
from .logger import *
from .semantic_version import *

# Ideally we could six.urllib but this causes problem with nosetests!
if six.PY2:
    import urlparse
elif six.PY3:
    import urllib.parse as urlparse

__all__ = ['Specification', 'Platform', 'ProjectIdentifier',
    'VersionOperator', 'VersionPredicate', 'parse_platforms']


class Specification(object):
    def __init__(self, identifier, predicate):
        self.identifier = identifier
        self.predicate = predicate
        self.raw_string = None

    @classmethod
    def cartfile_string(cls, string, overrides = None):
        # type: (str) -> Specification
        """
        >>> Specification.cartfile_string('github "foo/bar"')
        github "foo/bar"
        >>> Specification.cartfile_string('github "foo/bar" "master"').identifier
        foo/bar
        >>> Specification.cartfile_string('github "foo/bar" "master"').predicate
        "master"
        >>> Specification.cartfile_string('github "foo/bar" "master"')
        github "foo/bar" "master"
        >>> Specification.cartfile_string('github "foo/bar" >= 1.0').predicate
        >= 1.0
        >>> Specification.cartfile_string('github "ReactiveX/RxSwift" "some/branch"').identifier
        ReactiveX/RxSwift
        >>> Specification.cartfile_string('github "ReactiveX/RxSwift" "some/branch"').predicate
        "some/branch"
        >>> Specification.cartfile_string('git "file:///Users/example/Project" "some/branch"').identifier
        Project
        """

        match = re.match(r'^(?P<address>(?P<service>github|git)\s+"[^/]+/(?:.+?)")(?:\s+(?P<predicate>.+)?)?', string)
        if not match:
            raise Exception('Bad spec {}'.format(string))

        identifier = ProjectIdentifier.string(match.group('address'), overrides=overrides)
        predicate = VersionPredicate(match.group('predicate'))
        specification = Specification(identifier=identifier, predicate=predicate)
        specification.raw_string = string

        return specification

    def __repr__(self):
        parts = [self.identifier.full_identifier]
        if self.predicate:
            parts += [str(self.predicate)]
        return ' '.join(parts)

@functools.total_ordering
class ProjectIdentifier(object):
    @classmethod
    def string(cls, string, overrides=None):
        # type: (str) -> ProjectIdentifier
        """
        >>> ProjectIdentifier.string('github "foo/bar"')
        foo/bar
        >>> ProjectIdentifier.string('github "foo/bar"').team_name
        'foo'
        >>> ProjectIdentifier.string('github "foo/bar"').project_name
        'bar'
        >>> ProjectIdentifier.string('github "foo/bar"').identifier
        'foo/bar'
        >>> ProjectIdentifier.string('github "foo/bar"').full_identifier
        'github "foo/bar"'
        >>> ProjectIdentifier.string('git "file:///Users/example/Projects/Example-Project"')
        Example-Project
        """

        match = re.match(r'^(?P<source>github|git)\s+"(?P<link>.+)"', string)
        if not match:
            raise Exception('No match')

        source = match.group('source')
        link = match.group('link')

        if source == 'github':
            match = re.match(r'^(?P<team_name>[^/]+)/(?P<project_name>[^/]+)$', link)
            if not match:
                raise Exception('No match')
            team_name = match.group('team_name')
            project_name = match.group('project_name')
            remote_url = 'git@github.com:{}/{}.git'.format(team_name, project_name)
        elif source == 'git':
            team_name = None
            url_parts = urlparse.urlparse(link)
            path = Path(url_parts.path)
            project_name = path.stem
            remote_url = link
        else:
            raise Exception('No match')

        return ProjectIdentifier(source=source, remote_url=remote_url, team_name=team_name, project_name=project_name, overrides=overrides)

    def __init__(self, source=None, team_name=None, project_name=None, remote_url=None, overrides=None):
        self.source = source
        self.team_name = team_name
        self.project_name = project_name
        self.remote_url = remote_url
        if overrides and self.project_name in overrides:
            override_url = overrides[self.project_name]
            logger.info('Overriding {} with git URL {}'.format(self.project_name, override_url))
            self.remote_url = override_url

    @mproperty
    def full_identifier(self):
        if self.source == 'git':
            return '{} "{}"'.format(self.source, self.remote_url)
        elif self.source == 'github':
            return '{} "{}/{}"'.format(self.source, self.team_name, self.project_name)
        else:
            raise Exception("Unknown source")


    @mproperty
    def identifier(self):
        components = [] \
            + ([self.team_name] if self.team_name else []) \
            + [self.project_name]
        return '/'.join(components)

    def __repr__(self):
        return self.identifier

    def __eq__(self, other):
        """
        >>> ProjectIdentifier.string('github "foo/bar"') == ProjectIdentifier.string('github "foo/bar"')
        True
        """
        return self.identifier == other.identifier

    def __ne__(self, other):
        """
        >>> ProjectIdentifier.string('github "foo/bar"') != ProjectIdentifier.string('github "foo/bar2"')
        True
        """
        return not (self == other)

    def __lt__(self, other):
        """
        >>> ProjectIdentifier.string('github "foo/bar"') < ProjectIdentifier.string('github "foo/bar2"')
        True
        """
        return self.identifier < other.identifier

    def __hash__(self):
        """
        >>> hash(ProjectIdentifier.string('github "foo/bar"')) == hash(ProjectIdentifier.string('github "foo/bar"'))
        True
        >>> hash(ProjectIdentifier.string('github "foo/bar"')) != hash(ProjectIdentifier.string('github "foo/bar2"'))
        True
        """
        return hash(self.identifier)

    def matches(self, name_filter):
        # type: ([str]) -> bool

        if not name_filter:
            return True

        if self.project_name in name_filter:
            return True

        return False


class VersionOperator(Enum):
    commitish = 'commit-ish'
    any = '<any>'
    greater_than_or_equals = '>='
    equals = '=='
    semantic_greater_than_or_equals = '~>'


class VersionPredicate(object):
    def __init__(self, string):
        """
        >>> VersionPredicate('"master"')
        "master"
        >>> VersionPredicate('>= 1.0')
        >= 1.0
        >>> VersionPredicate('~> 1.0')
        ~> 1.0
        >>> VersionPredicate('== 1.0')
        == 1.0
        """

        if not string:
            self.operator = VersionOperator.any
            self.value = None
        else:
            match = re.match(r'(?:(~>|>=|==|)\s+)?(?:"(.+)"|(.+))', string)
            if not match:
                raise Exception('No match for: {}'.format(string))

            operator = match.group(1)
            value = match.group(2) if match.group(2) else match.group(3)

            if operator == '==':
                self.operator = VersionOperator.equals
                self.value = SemanticVersion.string(value)
            elif operator == '>=':
                self.operator = VersionOperator.greater_than_or_equals
                self.value = SemanticVersion.string(value)
            elif operator == '~>':
                self.operator = VersionOperator.semantic_greater_than_or_equals
                self.value = SemanticVersion.string(value)
            else:
                self.operator = VersionOperator.commitish
                self.value = value

    def __repr__(self):
        if self.operator == VersionOperator.any:
            return ''
        if self.operator == VersionOperator.commitish:
            return '"{}"'.format(self.value)
        elif self.operator == VersionOperator.equals:
            return '== {}'.format(self.value)
        elif self.operator == VersionOperator.greater_than_or_equals:
            return '>= {}'.format(self.value)
        elif self.operator == VersionOperator.semantic_greater_than_or_equals:
            return '~> {}'.format(self.value)

    def test(self, version):
        # type: (SemanticVersion) -> bool
        if self.operator == VersionOperator.any:
            return True
        elif self.operator == VersionOperator.equals:
            return version == self.value
        elif self.operator == VersionOperator.greater_than_or_equals:
            return version >= self.value
        elif self.operator == VersionOperator.semantic_greater_than_or_equals:
            return self.value <= version <= self.value.next_major
        return False


class Platform(object):

    all = []

    def __init__(self, name, nickname, sdks, output_directory_name):
        self.name = name
        self.nickname = nickname
        self.sdks = sdks
        self.output_directory_name = output_directory_name

    @classmethod
    def platform_for_nickname(cls, nickname):
        # type: (str) -> Platform
        for platform in cls.all:
            if platform.nickname.lower() == nickname.lower():
                return platform
        return None

    @property
    def device_sdk(self):
        return self.sdks[0]

    def __repr__(self):
        return self.nickname


Platform.all = [
    Platform(name='iOS', nickname='iOS', sdks=['iphoneos', 'iphonesimulator'], output_directory_name='iOS'),
    Platform(name='macOS', nickname='Mac', sdks=['macosx'], output_directory_name='Mac'),
    # TODO add watchos and tvos
]


def parse_platforms(s):
    # type: (str) -> [Platform]
    if not s:
        return Platform.all
    else:
        return [Platform.platform_for_nickname(platform.strip()) for platform in s.split(',')]
