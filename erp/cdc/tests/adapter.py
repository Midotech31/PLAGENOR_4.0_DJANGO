import functools
import inspect
import itertools
import unittest


def source_suite(module):
    suite = unittest.TestSuite()
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith('test_') or function.__module__ != module.__name__:
            continue
        cases = [{}]
        for marker in getattr(function, 'pytestmark', []):
            if marker.name != 'parametrize':
                raise RuntimeError('Unsupported source test marker: ' + marker.name)
            names = marker.args[0]
            names = [part.strip() for part in names.split(',')] if isinstance(names, str) else list(names)
            expanded = []
            for previous, values in itertools.product(cases, marker.args[1]):
                if len(names) == 1:
                    values = [values]
                expanded.append({**previous, **dict(zip(names, values, strict=True))})
            cases = expanded
        for index, parameters in enumerate(cases):
            invoke = functools.partial(function, **parameters)
            invoke.__name__ = name + '[' + str(index) + ']'
            suite.addTest(unittest.FunctionTestCase(invoke, description=module.__name__ + '.' + invoke.__name__))
    return suite
