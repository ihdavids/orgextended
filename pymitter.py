#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""
pymitter
Python port of the extended Node.js EventEmitter 2 approach providing
namespaces, wildcards and TTL.
"""


__author__     = "Marcel Rieger"
__copyright__  = "Copyright 2014, Marcel Rieger"
__credits__    = ["Marcel Rieger"]
__license__    = "MIT"
__maintainer__ = "Marcel Rieger"
__status__     = "Development"
__version__    = "0.2.3"
__all__        = ["EventEmitter"]


# python imports
from time import time


class EventEmitter(object):

    __CBKEY  = "__callbacks"
    __WCCHAR = "*"

    def __init__(self, **kwargs):
        """ EventEmitter(wildcard=False, delimiter=".", new_listener=False,
                         max_listeners=-1)
        The EventEmitter class.
        Please always use *kwargs* in the constructor.
        - *wildcard*: When *True*, wildcards are used.
        - *delimiter*: The delimiter to seperate event namespaces.
        - *new_listener*: When *True*, the "new_listener" event is emitted every
          time a new listener is registered with arguments *(func, event=None)*.
        - *max_listeners*: Maximum number of listeners per event. Negativ values
          mean infinity.
        """
        super(EventEmitter, self).__init__()

        self.wildcard      = kwargs.get("wildcard", False)
        self.__delimiter   = kwargs.get("delimiter", ".")
        self.new_listener  = kwargs.get("new_listener", False)
        self.max_listeners = kwargs.get("max_listeners", -1)

        self.__tree = self.__new_branch()

    @property
    def delimiter(self):
        """
        *delimiter* getter.
        """
        return self.__delimiter

    @classmethod
    def __new_branch(cls):
        """
        Returns a new branch. Basically, a branch is just a dictionary with
        a special item *__CBKEY* that holds registered functions. All other
        items are used to build a tree structure.
        """
        return { cls.__CBKEY: [] }

    def __find_branch(self, event):
        """
        Returns a branch of the tree stucture that matches *event*. Wildcards
        are not applied.
        """
        parts = event.split(self.delimiter)

        if self.__CBKEY in parts:
            return None

        branch = self.__tree
        for p in parts:
            if p not in branch:
                return None
            branch = branch[p]

        return branch

    @classmethod
    def __remove_listener(cls, branch, func):
        """
        Removes a listener given by its function from a branch.
        """
        listeners = branch[cls.__CBKEY]

        indexes = [i for i, l in enumerate(listeners) if l.func == func]
        indexes.reverse()

        for i in indexes:
            listeners.pop(i)

    @classmethod
    def __remove_all_listeners(cls, branch):
        """
        Removes a listener given by its function from a branch.
        """
        listeners = branch[cls.__CBKEY]

        indexes = [i for i, l in enumerate(listeners)]
        indexes.reverse()

        for i in indexes:
            listeners.pop(i)

    def on(self, event, func=None, ttl=-1):
        """
        Registers a function to an event. When *func* is *None*, decorator
        usage is assumed. *ttl* defines the times to listen. Negative values
        mean infinity. Returns the function.
        """
        def _on(func):
            if not hasattr(func, "__call__"):
                return func

            parts = event.split(self.delimiter)

            if self.__CBKEY in parts:
                return func

            branch = self.__tree
            for p in parts:
                branch = branch.setdefault(p, self.__new_branch())

            listeners = branch[self.__CBKEY]

            if 0 <= self.max_listeners <= len(listeners):
                return func

            listener = Listener(func, event, ttl)
            listeners.append(listener)

            if self.new_listener:
                self.emit("new_listener", func, event)

            return func

        if func is not None:
            return _on(func)
        else:
            return _on

    def once(self, *args, **kwargs):
        """
        Registers a function to an event with *ttl = 1*. See *on*. Returns the
        function.
        """
        if len(args) == 3:
            args[2] = 1
        else:
            kwargs["ttl"] = 1
        return self.on(*args, **kwargs)

    def on_any(self, func=None):
        """
        Registers a function that is called every time an event is emitted.
        When *func* is *None*, decorator usage is assumed. Returns the function.
        """
        def _on_any(func):
            if not hasattr(func, "__call__"):
                return func

            listeners = self.__tree[self.__CBKEY]

            if 0 <= self.max_listeners <= len(listeners):
                return func

            listener = Listener(func, None, -1)
            listeners.append(listener)

            if self.new_listener:
                self.emit("new_listener", func)

            return func

        if func is not None:
            return _on_any(func)
        else:
            return _on_any


    def clear_listeners(self, event):
        branch = self.__find_branch(event)
        if branch is None:
            return
        self.__remove_all_listeners(branch)


    def off(self, event, func=None):
        """
        Removes a function that is registered to an event. When *func* is
        *None*, decorator usage is assumed. Returns the function.
        """
        def _off(func):
            branch = self.__find_branch(event)
            if branch is None:
                return func

            self.__remove_listener(branch, func)

            return func

        if func is not None:
            return _off(func)
        else:
            return _off

    def off_any(self, func=None):
        """
        Removes a function that was registered via *on_any*. When *func* is
        *None*, decorator usage is assumed. Returns the function.
        """
        def _off_any(func):
            self.__remove_listener(self.__tree, func)

            return func

        if func is not None:
            return _off_any(func)
        else:
            return _off_any

    def off_all(self):
        """
        Removes all registerd functions.
        """
        del self.__tree
        self.__tree = self.__new_branch()

    def listeners(self, event):
        """
        Returns all functions that are registered to an event. Wildcards are not
        applied.
        """
        branch = self.__find_branch(event)
        if branch is None:
            return []

        return [l.func for l in branch[self.__CBKEY]]

    def listeners_any(self):
        """
        Returns all functions that were registered using *on_any*.
        """
        return [l.func for l in self.__tree[self.__CBKEY]]

    def listeners_all(self):
        """
        Returns all registered functions.
        """
        listeners = self.__tree[self.__CBKEY][:]

        branches = self.__tree.values()
        for b in branches:
            if not isinstance(b, dict):
                continue

            branches.extend(b.values())

            listeners.extend(b[self.__CBKEY])

        return [l.func for l in listeners]

    def emit(self, event, *args, **kwargs):
        """
        Emits an event. All functions of events that match *event* are invoked
        with *args* and *kwargs* in the exact order of their registration.
        Wildcards might be applied.
        """
        parts = event.split(self.delimiter)

        if self.__CBKEY in parts:
            return

        listeners = self.__tree[self.__CBKEY][:]

        branches = [self.__tree]

        for p in parts:
            _branches = []
            for branch in branches:
                for k, b in branch.items():
                    if k == self.__CBKEY:
                        continue
                    if k == p:
                        _branches.append(b)
                    elif self.wildcard:
                        if p == self.__WCCHAR or k == self.__WCCHAR:
                            _branches.append(b)
            branches = _branches

        for b in branches:
            listeners.extend(b[self.__CBKEY])

        listeners.sort(key=lambda l: l.time)

        remove = [l for l in listeners if not l(*args, **kwargs)]

        for l in remove:
            self.off(l.event, func=l.func)


class Listener(object):

    def __init__(self, func, event, ttl):
        """
        The Listener class.
        Listener instances are simple structs to handle functions and their ttl
        values.
        """
        super(Listener, self).__init__()

        self.func  = func
        self.event = event
        self.ttl   = ttl

        self.time = time()

    def __call__(self, *args, **kwargs):
        """
        Invokes the wrapped function. If the ttl value is non-negative, it is
        decremented by 1. In this case, returns *False* if the ttl value
        approached 0. Returns *True* otherwise.
        """
        self.func(*args, **kwargs)

        if self.ttl > 0:
            self.ttl -= 1
            if self.ttl == 0:
                return False

        return True




eventEmitter = EventEmitter()

def Get():
    return eventEmitter

def EmitIf(onDone):
    if(onDone):
        eventEmitter.emit(onDone)


import OrgExtended.orgutil.util as util

def Make(func):
    eventName = util.RandomString()
    eventEmitter.once(eventName, func)
    return eventName
