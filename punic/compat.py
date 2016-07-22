import sys

# support unicode in Python 2 and Python 3
if sys.version_info < (3,):
    def safe_unicode(s, encoding='utf-8'):
        return unicode(s, encoding=encoding)
else:
    def safe_unicode(s, encoding=None):
        return s