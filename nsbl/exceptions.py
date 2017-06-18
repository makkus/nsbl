# -*- coding: utf-8 -*-


class NsblException(Exception):
    """Base exception class for nsbl."""

    def __init__(self, message):
        super(NsblException, self).__init__(message)
