import os
from functools import wraps # This convenience func preserves name and docstring


# Decorator that helps me extend classes.
# I am using this to extend sublime a bit
# and add some mechanisms to orgparse without
# adding sublime specific components to node.
def add_method(cls):
    def decorator(func):
        setattr(cls, func.__name__, func)
    return decorator
