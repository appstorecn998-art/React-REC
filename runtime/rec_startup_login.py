"""Compatibility entry point for the single-user local REC workspace."""


def startup_login(publisher_factory, client_factory=None):
    window = publisher_factory()
    window.show()
    return window
