#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2014 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

import doctest
import unittest
import timeit

from compas.dispatcher import Dispatcher
from compas.dispatcher.constants import START, EMPTY, SINK, NONE


def _setup_dsp():
    dsp = Dispatcher()

    dsp.add_function('min', min, inputs=['a', 'c'], outputs=['d'])
    dsp.add_function('max', max, inputs=['b', 'd'], outputs=['c'])
    dsp.add_data(data_id='e')

    from math import log, pow

    def my_log(a, b):
        return log(b - a)

    def log_dom(a, b):
        return a < b

    dsp.add_function('log(b - a)', function=my_log, inputs=['a', 'b'],
                     outputs=['c'], input_domain=log_dom)

    def _2x(d):
        return 2 / (d + 1)

    def _2x_dom(d):
        return d != -1

    dsp.add_function('2 / (d + 1)', function=_2x, inputs=['d'],
                     outputs=['e'], input_domain=_2x_dom)

    def x_4(a):
        return a - 4

    dsp.add_function('x - 4', function=x_4, inputs=['a'],
                     outputs=['d'], weight_from={'a': 20},
                     weight_to={'d': 20}, weight=20)

    def x_y(e, d):
        return pow(e, d)

    def x_y_dom(x, y):
        return not x == y == 0

    dsp.add_function('x ^ y', function=x_y, inputs=['e', 'd'],
                     outputs=['b'], input_domain=x_y_dom)

    return dsp


class TestDoctest(unittest.TestCase):
    def runTest(self):
        import compas.dispatcher as d

        failure_count, test_count = doctest.testmod(
            d, optionflags=doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS
        )
        self.assertGreater(test_count, 0, (failure_count, test_count))
        self.assertEqual(failure_count, 0, (failure_count, test_count))


class TestCreateDispatcher(unittest.TestCase):
    def test_add_data(self):
        dsp = Dispatcher()

        self.assertEqual(dsp.add_data(data_id='a'), 'a')
        self.assertEqual(dsp.add_data(data_id='a'), 'a')
        self.assertEqual(dsp.add_data(), 'unknown<0>')

        self.assertEqual(dsp.add_data(default_value='v'), 'unknown<1>')
        self.assertEqual(dsp.dmap.node['unknown<1>'], {'wait_inputs': False,
                                                       'type': 'data'})
        self.assertEqual(dsp.default_values['unknown<1>'], 'v')

        self.assertEqual(dsp.add_data(data_id='unknown<1>'), 'unknown<1>')
        self.assertFalse('unknown<1>' in dsp.default_values)

        dsp.add_data(data_id='a', wait_inputs=False, function=lambda: None,
                     callback=lambda: None, wildcard=True)
        res = ['callback', 'function', 'wildcard', 'wait_inputs', 'type']
        self.assertEqual(set(dsp.dmap.node['a'].keys()), set(res))

        dsp.add_function(function_id='fun', inputs=['a'])
        self.assertRaises(ValueError, dsp.add_data, *('fun', ))

    def test_add_function(self):
        dsp = Dispatcher()

        def my_function(a, b):
            return a + b, a - b

        fun_id = dsp.add_function(function=my_function, inputs=['a', 'b'],
                                  outputs=['c', 'd'])

        self.assertEqual(fun_id, '%s:my_function' % __name__)

        from math import log

        def my_log(a, b):
            log(b - a)

        def my_domain(a, b):
            return a < b

        fun_id = dsp.add_function(function_id='funny_id', function=my_log,
                                  inputs=['a', 'b'], outputs=['e'],
                                  input_domain=my_domain, weight=1,
                                  weight_from={'a': 2, 'b': 3},
                                  weight_to={'e': 4})

        self.assertEqual(fun_id, 'funny_id')
        res = {
            'a': {'wait_inputs': False, 'type': 'data'},
            'b': {'wait_inputs': False, 'type': 'data'},
            'c': {'wait_inputs': False, 'type': 'data'},
            'd': {'wait_inputs': False, 'type': 'data'},
            'e': {'wait_inputs': False, 'type': 'data'},
            '%s:my_function' % __name__: {
                'type': 'function',
                'inputs': ['a', 'b'],
                'function': my_function,
                'outputs': ['c', 'd'],
                'wait_inputs': True},
            'funny_id': {
                'type': 'function',
                'inputs': ['a', 'b'],
                'function': my_log,
                'input_domain': my_domain,
                'outputs': ['e'],
                'weight': 1,
                'wait_inputs': True},
        }
        self.assertEqual(dsp.dmap.node, res)
        res = [dsp.dmap.edge['a']['funny_id']['weight'],
               dsp.dmap.edge['b']['funny_id']['weight'],
               dsp.dmap.edge['funny_id']['e']['weight']]
        self.assertEqual(res, [2, 3, 4])

        fun_id = dsp.add_function(function_id='funny_id', inputs=['a'])
        self.assertEqual(fun_id, 'funny_id<0>')
        res = {
            'type': 'function',
            'inputs': ['a'],
            'function': None,
            'outputs': [SINK],
            'wait_inputs': True
        }
        self.assertEqual(dsp.dmap.node[fun_id], res)

        self.assertRaises(ValueError, dsp.add_function)
        self.assertRaises(ValueError, dsp.add_function, inputs=['a'])
        self.assertRaises(ValueError, dsp.add_function, 'f', inputs=[fun_id])
        self.assertRaises(ValueError, dsp.add_function, 'f', outputs=[fun_id])

    def test_load_from_lists(self):
        dsp = Dispatcher()
        self.assertEqual(dsp.add_from_lists(), ([], []))

        def fun(**kwargs):
            return (kwargs['a'] + kwargs['b']) / 2

        def callback(value):
            print(value)

        data_list = [
            {'data_id': 'a', 'default_value': 0, 'callback': callback},
            {'data_id': 'b'},
            {'data_id': 'c', 'wait_inputs': True, 'wildcard': True,
             'function': fun}
        ]

        def fun1(a, b):
            return a + b

        fun_list = [
            {'function': fun1, 'inputs': ['a', 'b'], 'outputs': ['c']},
        ]
        dsp.add_from_lists(data_list, fun_list)
        res = {
            'a': {'wait_inputs': False, 'callback': callback, 'type': 'data'},
            'b': {'wait_inputs': False, 'type': 'data'},
            'c': {'wait_inputs': True, 'function': fun, 'type': 'data',
                  'wildcard': True},
            '%s:fun1' % __name__: {'inputs': ['a', 'b'],
                                'wait_inputs': True,
                                'function': fun1,
                                'type': 'function',
                                'outputs': ['c']},
        }
        self.assertEqual(dsp.dmap.node, res)

    def test_set_default_value(self):
        dsp = Dispatcher()

        dsp.add_data('a', default_value=1)
        self.assertEqual(dsp.default_values['a'], 1)

        dsp.set_default_value('a', value=2)
        self.assertEqual(dsp.default_values['a'], 2)

        dsp.set_default_value('a', value=EMPTY)
        self.assertFalse('a' in dsp.default_values)

        self.assertRaises(ValueError, dsp.set_default_value, *('b', 3))

        fun_id = dsp.add_function(function=max, inputs=['a', 'b'])
        self.assertRaises(ValueError, dsp.set_default_value, *(fun_id, ))

        dsp.set_default_value('b', value=3)
        self.assertEqual(dsp.default_values['b'], 3)


class TestSubDMap(unittest.TestCase):
    def setUp(self):
        dsp = Dispatcher()
        dsp.add_data(data_id='b', wait_inputs=True, default_value=3)

        dsp.add_function('max', inputs=['a', 'b'], outputs=['c'])
        dsp.add_function('min', inputs=['a', 'c'], outputs=['d'])
        dsp.add_function('min<0>', inputs=['b', 'd'], outputs=['c'])
        dsp.add_function('max<0>', inputs=['b', 'd'], outputs=['a'])
        dsp.add_data(data_id='e')
        dsp.dispatch(['a', 'b'], no_call=True)
        self.dsp = dsp

    def test_get_sub_dmap(self):

        dsp = self.dsp
        sub_dmap = dsp.get_sub_dsp(['a', 'b', 'c', 'max', 'max<0>'])
        res = {
            'a': {'type': 'data', 'wait_inputs': False},
            'b': {'type': 'data', 'wait_inputs': True},
            'c': {'type': 'data', 'wait_inputs': False},
            'max': {'function': None,
                    'inputs': ['a', 'b'],
                    'outputs': ['c'],
                    'type': 'function',
                    'wait_inputs': True}
        }
        self.assertEqual(sub_dmap.dmap.node, res)
        self.assertEqual(sub_dmap.default_values['b'], 3)

        sub_dmap = dsp.get_sub_dsp(['a', 'c', 'max', 'max<0>'])
        self.assertEqual(sub_dmap.dmap.node, {})

        sub_dmap = dsp.get_sub_dsp(['a', 'b', 'c', 'max', 'e'])
        res = {
            'a': {'type': 'data', 'wait_inputs': False},
            'b': {'type': 'data', 'wait_inputs': True},
            'c': {'type': 'data', 'wait_inputs': False},
            'max': {'function': None,
                    'inputs': ['a', 'b'],
                    'outputs': ['c'],
                    'type': 'function',
                    'wait_inputs': True}
        }
        self.assertEqual(sub_dmap.dmap.node, res)
        self.assertEqual(sub_dmap.default_values['b'], 3)

        edges_bunch = [('max', 'c')]
        sub_dmap = dsp.get_sub_dsp(['a', 'b', 'c', 'max'], edges_bunch)
        self.assertEqual(sub_dmap.dmap.node, {})

    def test_get_sub_dmap_from_workflow(self):
        dsp = self.dsp

        sub_dmap = dsp.get_sub_dsp_from_workflow(['a', 'b'])
        res = {
            'd': {'type': 'data', 'wait_inputs': False},
            'c': {'type': 'data', 'wait_inputs': False},
            'min': {
                'type': 'function',
                'wait_inputs': True,
                'inputs': ['a', 'c'],
                'function': None,
                'outputs': ['d']
            },
            'a': {'type': 'data', 'wait_inputs': False},
            'max': {
                'type': 'function',
                'wait_inputs': True,
                'inputs': ['a', 'b'],
                'function': None,
                'outputs': ['c']
            },
            'b': {'type': 'data', 'wait_inputs': True}
        }
        self.assertEqual(sub_dmap.dmap.node, res)

        sub_dmap = dsp.get_sub_dsp_from_workflow(['d'], reverse=True)
        self.assertEqual(sub_dmap.dmap.node, res)

        sub_dmap = dsp.get_sub_dsp_from_workflow(['c'], reverse=True)
        res.pop('min')
        res.pop('d')
        self.assertEqual(sub_dmap.dmap.node, res)

        sub_dmap = dsp.get_sub_dsp_from_workflow(['c', 'e'], reverse=True)
        self.assertEqual(sub_dmap.dmap.node, res)
        self.assertEqual(sub_dmap.default_values['b'], 3)


class TestPerformance(unittest.TestCase):
    def test_stress_tests(self):
        res = timeit.repeat(
            "dsp.dispatch({'a': 5, 'b': 6})",
            'from %s import _setup_dsp; '
            'dsp = _setup_dsp()' % __name__,
            repeat=3, number=1000)
        res = sum(res) / 3
        print('dispatch with functions in %f ms/call' % res)

        res1 = timeit.repeat(
            "dsp.dispatch({'a': 5, 'b': 6}, no_call=True)",
            'from %s import _setup_dsp; '
            'dsp = _setup_dsp()' % __name__,
            repeat=3, number=1000)
        res1 = sum(res1) / 3
        print('dispatch without functions in %f ms/call' % res1)
        diff = res - res1
        print('functions is %f ms/call' % diff)

        res2 = timeit.repeat(
            "fun(5, 6)",
            'from %s import _setup_dsp;'
            'from compas.dispatcher.utils.dsp import SubDispatchFunction;'
            'dsp = _setup_dsp();'
            'fun = SubDispatchFunction(dsp, "f", ["a", "b"], ["c", "d", "e"])'
            % __name__,
            repeat=3, number=1000)

        res2 = sum(res2) / 3
        print('dispatcher function with functions in %f ms/call' % res2)
        print('dispatcher function without functions in '
              '%f ms/call' % (res2 - diff))


class TestDispatch(unittest.TestCase):
    def setUp(self):
        self.dsp = _setup_dsp()
        self.dsp_cutoff = _setup_dsp()
        self.dsp_wildcard_1 = _setup_dsp()
        self.dsp_wildcard_2 = _setup_dsp()

        def average(kwargs):
            return sum(kwargs.values()) / len(kwargs)

        self.dsp_wildcard_1.dmap.node['b']['wait_inputs'] = True
        self.dsp_wildcard_1.dmap.node['b']['function'] = average

        self.dsp_wildcard_2.dmap.edge['e']['x ^ y']['weight'] = -100

        self.dsp_raises = Dispatcher(raises=True)
        from math import log
        self.dsp_raises.add_function(function=log, inputs=['a'], outputs=['b'])

    def test_without_outputs(self):
        dsp = self.dsp

        wk, o = dsp.dispatch({'a': 5, 'b': 6, 'f': 9})
        r = ['2 / (d + 1)', 'a', 'b', 'c', 'd', 'e', 'log(b - a)', 'min', START]
        w = {
            'a': {'log(b - a)': {'value': 5}, 'min': {'value': 5}},
            'b': {'log(b - a)': {'value': 6}},
            'c': {'min': {'value': 0.0}},
            'd': {'2 / (d + 1)': {'value': 0.0}},
            'e': {},
            '2 / (d + 1)': {'e': {'value': 2.0}},
            'log(b - a)': {'c': {'value': 0.0}},
            'min': {'d': {'value': 0.0}},
            START: {'a': {'value': 5}, 'b': {'value': 6}}
        }
        self.assertEqual(o, {'a': 5, 'b': 6, 'c': 0, 'd': 0, 'e': 2, 'f': 9})
        self.assertEqual(sorted(list(wk.node)), r)
        self.assertEqual(wk.edge, w)

        wk, o = dsp.dispatch({'a': 5, 'b': 3})
        r = ['2 / (d + 1)', 'a', 'b', 'c', 'd', 'e', 'log(b - a)', 'max', START,
             'x - 4']
        w = {
            'a': {'log(b - a)': {'value': 5}, 'x - 4': {'value': 5}},
            'b': {'log(b - a)': {'value': 3}, 'max': {'value': 3}},
            'c': {},
            'd': {'2 / (d + 1)': {'value': 1}, 'max': {'value': 1}},
            'e': {},
            '2 / (d + 1)': {'e': {'value': 1.0}},
            'log(b - a)': {},
            'max': {'c': {'value': 3}},
            START: {'a': {'value': 5}, 'b': {'value': 3}},
            'x - 4': {'d': {'value': 1}}
        }
        self.assertEqual(o, {'a': 5, 'b': 3, 'c': 3, 'd': 1, 'e': 1})
        self.assertEqual(sorted(list(wk.node)), r)
        self.assertEqual(wk.edge, w)

    def test_no_call(self):
        dsp = self.dsp
        wk, o = dsp.dispatch(['a', 'b'], no_call=True)
        r = ['2 / (d + 1)', 'a', 'b', 'c', 'd', 'e', 'log(b - a)', 'min', START]
        w = {
            'a': {'log(b - a)': {}, 'min': {}},
            'b': {'log(b - a)': {}},
            'c': {'min': {}},
            'd': {'2 / (d + 1)': {}},
            'e': {},
            '2 / (d + 1)': {'e': {}},
            'log(b - a)': {'c': {}},
            'min': {'d': {}},
            START: {'a': {}, 'b': {}}
        }
        self.assertEqual(o, dict.fromkeys(['a', 'b', 'c', 'd', 'e'], NONE))
        self.assertEqual(sorted(list(wk.node)), r)
        self.assertEqual(wk.edge, w)

    def test_with_outputs(self):
        dsp = self.dsp

        wk, o = dsp.dispatch({'a': 5, 'b': 6}, ['d'])
        r = ['a', 'b', 'c', 'd', 'log(b - a)', 'min', START]
        w = {
            'a': {'log(b - a)': {'value': 5}, 'min': {'value': 5}},
            'b': {'log(b - a)': {'value': 6}},
            'c': {'min': {'value': 0.0}},
            'd': {},
            'log(b - a)': {'c': {'value': 0.0}},
            'min': {'d': {'value': 0.0}},
            START: {'a': {'value': 5}, 'b': {'value': 6}}
        }
        self.assertEqual(o, {'a': 5, 'b': 6, 'c': 0, 'd': 0})
        self.assertEqual(sorted(list(wk.node)), r)
        self.assertEqual(wk.edge, w)

    def test_cutoff(self):
        dsp = self.dsp_cutoff

        wk, o = dsp.dispatch({'a': 5, 'b': 6}, cutoff=2)
        r = ['a', 'b', 'c', 'log(b - a)', START]
        w = {
            'a': {'log(b - a)': {'value': 5}},
            'b': {'log(b - a)': {'value': 6}},
            'c': {},
            'log(b - a)': {'c': {'value': 0.0}},
            START: {'a': {'value': 5}, 'b': {'value': 6}}
        }
        self.assertEqual(o, {'a': 5, 'b': 6, 'c': 0})
        self.assertEqual(sorted(list(wk.node)), r)
        self.assertEqual(wk.edge, w)

        dsp.weight = None
        wk, o = dsp.dispatch({'a': 5, 'b': 6}, cutoff=2)
        r = ['a', 'b', 'c', 'd', 'log(b - a)', START, 'x - 4']
        w = {
            'a': {'log(b - a)': {'value': 5}, 'x - 4': {'value': 5}},
            'b': {'log(b - a)': {'value': 6}},
            'c': {},
            'd': {},
            'log(b - a)': {'c': {'value': 0.0}},
            'x - 4': {'d': {'value': 1}},
            START: {'a': {'value': 5}, 'b': {'value': 6}}
        }
        self.assertEqual(o, {'a': 5, 'b': 6, 'c': 0, 'd': 1})
        self.assertEqual(sorted(list(wk.node)), r)
        self.assertEqual(wk.edge, w)

    def test_wildcard(self):
        dsp = self.dsp
        wk, o = dsp.dispatch({'a': 5, 'b': 6}, ['a', 'b'], wildcard=True)
        r = ['2 / (d + 1)', 'a', 'b', 'c', 'd', 'e', 'log(b - a)', 'min', START,
             'x ^ y']
        w = {
            'a': {'log(b - a)': {'value': 5}, 'min': {'value': 5}},
            'b': {'log(b - a)': {'value': 6}},
            'c': {'min': {'value': 0.0}},
            'd': {'2 / (d + 1)': {'value': 0.0}, 'x ^ y': {'value': 0.0}},
            'e': {'x ^ y': {'value': 2.0}},
            '2 / (d + 1)': {'e': {'value': 2.0}},
            'log(b - a)': {'c': {'value': 0.0}},
            'min': {'d': {'value': 0.0}},
            START: {'a': {'value': 5}, 'b': {'value': 6}},
            'x ^ y': {'b': {'value': 1.0}}
        }
        self.assertEqual(o, {'b': 1, 'c': 0, 'd': 0, 'e': 2})
        self.assertEqual(sorted(list(wk.node)), r)
        self.assertEqual(wk.edge, w)

        dsp = self.dsp_wildcard_1

        wk, o = dsp.dispatch({'a': 5, 'b': 6}, ['a', 'b'], wildcard=True)
        self.assertEqual(sorted(list(wk.node)), r)
        self.assertEqual(wk.edge, w)

        dsp = self.dsp_wildcard_2
        self.assertRaises(ValueError, dsp.dispatch, {'a': 5, 'b': 6},
                          ['a', 'b'], wildcard=True)

    def test_raises(self):
        dsp = self.dsp_raises
        self.assertRaises(ValueError, dsp.dispatch, inputs={'a': 0})


class TestBoundaryDispatch(unittest.TestCase):
    def setUp(self):
        self.dsp = Dispatcher()

        def f(*args):
            return 3, 5

        self.dsp.add_function(function=f, outputs=['a', SINK])
        self.dsp.add_function(function=f, outputs=[SINK, 'b'])

        self.dsp_1 = Dispatcher()
        self.dsp_1.add_function('A', max, inputs=['a', 'b'], outputs=['c'])
        self.dsp_1.add_function('B', min, inputs=['a', 'b'], outputs=['c'])

        self.dsp_2 = Dispatcher()
        self.dsp_2.add_function('B', max, inputs=['a', 'b'], outputs=['c'])
        self.dsp_2.add_function('A', min, inputs=['a', 'b'], outputs=['c'])

        self.dsp_3 = Dispatcher()

        def f(kwargs):
            return 1 / list(kwargs.values())[0]

        self.dsp_3.add_function('A', min, inputs=['a', 'b'], outputs=['c'])
        self.dsp_3.add_data('c', function=f, callback=f)

    def test_dispatch_functions_without_arguments(self):
        dsp = self.dsp
        self.assertEqual(dsp.dispatch(outputs=['a', 'b'])[1], {'a': 3, 'b': 5})

    def test_deterministic_dispatch(self):
        dsp = self.dsp_1

        o = dsp.dispatch(inputs={'a': 1, 'b': 3})[1]
        self.assertEqual(o, {'a': 1, 'b': 3, 'c': 3})

        dsp = self.dsp_2

        o = dsp.dispatch(inputs={'a': 1, 'b': 3})[1]
        self.assertEqual(o, {'a': 1, 'b': 3, 'c': 1})

    def test_callback(self):
        dsp = self.dsp_3
        o = dsp.dispatch(inputs={'a': 1, 'b': 5})[1]
        self.assertEqual(o, {'a': 1, 'b': 5, 'c': 1.0})

        o = dsp.dispatch(inputs={'a': 0, 'b': 5})[1]
        self.assertEqual(o, {'a': 0, 'b': 5})


class TestNodeOutput(unittest.TestCase):
    def setUp(self):


        dsp = Dispatcher()

        dsp.add_data('a', default_value=[1, 2])
        dsp.add_function('max', max, inputs=['a'], outputs=['b'])
        dsp.add_function('max', inputs=['a'], outputs=['b'])
        dsp.add_function('max', max, inputs=['a'], outputs=['c'])
        dsp.workflow.add_node(START, attr_dict={'type': 'start'})
        dsp.workflow.add_edge(START, 'a', attr_dict={'value': [1, 2]})

        dsp.add_data('b', wait_inputs=True)

        self.callback_obj = set()

        def callback(value):
            self.callback_obj.update([value])

        dsp.add_data('c', callback=callback)
        self.dsp = dsp

    def test_set_node_output(self):
        dsp = self.dsp
        wf_edge = dsp.workflow.edge
        data_out = dsp.data_output
        self.assertTrue(dsp._set_node_output('a', False))
        r = {
            'a': {
                'max': {'value': [1, 2]},
                'max<0>': {'value': [1, 2]},
                'max<1>': {'value': [1, 2]}
            },
            'max': {},
            'max<0>': {},
            'max<1>': {},
            START: {'a': {'value': [1, 2]}}
        }
        self.assertEqual(wf_edge, r)
        self.assertEqual(data_out, {'a': [1, 2]})

        self.assertFalse(dsp._set_node_output('max<0>', False))
        self.assertTrue(dsp._set_node_output('max', False))
        r['b'] = {}
        r['max'] = {'b': {'value': 2}}

        self.assertEqual(wf_edge, r)
        self.assertEqual(data_out, {'a': [1, 2]})

        self.assertFalse(dsp._set_node_output('b', False))
        self.assertEqual(wf_edge, r)
        self.assertEqual(data_out, {'a': [1, 2]})

        self.assertTrue(dsp._set_node_output('max<1>', False))
        self.assertTrue(dsp._set_node_output('c', False))
        r['c'] = {}
        r['max<1>'] = {'c': {'value': 2}}
        self.assertEqual(wf_edge, r)
        self.assertEqual(data_out, {'a': [1, 2], 'c': 2})
        self.assertEqual(self.callback_obj, {2})


class TestShrinkDispatcher(unittest.TestCase):
    def setUp(self):
        dsp = Dispatcher()
        dsp.add_function(function_id='h', inputs=['a', 'b'], outputs=['c'])
        dsp.add_function(function_id='h', inputs=['b', 'd'], outputs=['e'])
        dsp.add_function(function_id='h', inputs=['d', 'e'], outputs=['c', 'f'])
        dsp.add_function(function_id='h', inputs=['d', 'f'], outputs=['g'])
        dsp.add_function(function_id='h', inputs=['a', 'b'], outputs=['a'])
        self.dsp_1 = dsp

        dsp = Dispatcher()
        dsp.add_function(function_id='h', inputs=['a'], outputs=['b'])
        dsp.add_function(function_id='h', inputs=['b'], outputs=['c'])
        dsp.add_function(function_id='h', inputs=['c'], outputs=['d'])
        dsp.add_function(function_id='h', inputs=['d'], outputs=['e'])
        dsp.add_function(function_id='h', inputs=['e'], outputs=['a'])
        self.dsp_2 = dsp

        dsp = Dispatcher()
        dsp.add_function(
            function_id='h', input_domain=bool, inputs=['a', 'b'], outputs=['g']
        )
        dsp.add_function(
            function_id='h', input_domain=bool, inputs=['b', 'c'], outputs=['g']
        )
        dsp.add_function(
            function_id='h', input_domain=bool, inputs=['c', 'd'], outputs=['g']
        )
        dsp.add_function(
            function_id='h', input_domain=bool, inputs=['e', 'f'], outputs=['g']
        )
        dsp.add_function(function_id='h', inputs=['g'], outputs=['i'])
        dsp.add_function(function_id='h', inputs=['g', 'd'], outputs=['i'])
        dsp.add_function(function_id='h', inputs=['i'], outputs=['l'])
        dsp.add_data('i', wait_inputs=True)
        self.dsp_3 = dsp

    def test_shrink_with_inputs_outputs(self):

        dsp = self.dsp_1
        shrink_dsp = dsp.shrink_dsp(['a', 'b', 'd'], ['c', 'a', 'f'])
        r = ['a', 'b', 'c', 'd', 'e', 'f', 'h', 'h<0>', 'h<1>', 'h<3>']
        w = [('a', 'h'), ('a', 'h<3>'), ('b', 'h'), ('b', 'h<0>'),
             ('b', 'h<3>'), ('d', 'h<0>'), ('d', 'h<1>'), ('e', 'h<1>'),
             ('h', 'c'), ('h<0>', 'e'), ('h<1>', 'f'), ('h<3>', 'a')]
        self.assertEqual(sorted(shrink_dsp.dmap.node), r)
        self.assertEqual(sorted(shrink_dsp.dmap.edges()), w)

        shrink_dsp = dsp.shrink_dsp(['a', 'b'], ['e'])
        self.assertEqual(sorted(shrink_dsp.dmap.node), [])
        self.assertEqual(sorted(shrink_dsp.dmap.edges()), [])

        shrink_dsp = dsp.shrink_dsp([], [])
        self.assertEqual(sorted(shrink_dsp.dmap.node), [])
        self.assertEqual(sorted(shrink_dsp.dmap.edges()), [])

        dsp = self.dsp_2
        shrink_dsp = dsp.shrink_dsp(['a'], ['b'])
        r = ['a', 'b', 'h']
        w = [('a', 'h'), ('h', 'b')]
        self.assertEqual(sorted(shrink_dsp.dmap.node), r)
        self.assertEqual(sorted(shrink_dsp.dmap.edges()), w)

    def test_shrink_with_outputs(self):
        dsp = self.dsp_1
        shrink_dsp = dsp.shrink_dsp(outputs=['g'])
        r = ['b', 'd', 'e', 'f', 'g', 'h<0>', 'h<1>', 'h<2>']
        w = [('b', 'h<0>'), ('d', 'h<0>'), ('d', 'h<1>'), ('d', 'h<2>'),
             ('e', 'h<1>'), ('f', 'h<2>'), ('h<0>', 'e'), ('h<1>', 'f'),
             ('h<2>', 'g')]
        self.assertEqual(sorted(shrink_dsp.dmap.node), r)
        self.assertEqual(sorted(shrink_dsp.dmap.edges()), w)

    def test_shrink_with_inputs(self):
        dsp = self.dsp_1
        shrink_dsp = dsp.shrink_dsp(inputs=['d', 'e'])
        r = ['c', 'd', 'e', 'f', 'g', 'h<1>', 'h<2>']
        w = [('d', 'h<1>'), ('d', 'h<2>'), ('e', 'h<1>'), ('f', 'h<2>'),
             ('h<1>', 'c'), ('h<1>', 'f'), ('h<2>', 'g')]
        self.assertEqual(sorted(shrink_dsp.dmap.node), r)
        self.assertEqual(sorted(shrink_dsp.dmap.edges()), w)

    def test_shrink_with_domains(self):
        dsp = self.dsp_3
        shrink_dsp = dsp.shrink_dsp(['a', 'b', 'c', 'e', 'f'])
        r = ['a', 'b', 'c', 'e', 'f', 'g', 'h', 'h<0>', 'h<2>', 'h<3>', 'h<5>',
             'i', 'l']
        w = [('a', 'h'), ('b', 'h'), ('b', 'h<0>'), ('c', 'h<0>'),
             ('e', 'h<2>'), ('f', 'h<2>'), ('g', 'h<3>'), ('h', 'g'),
             ('h<0>', 'g'), ('h<2>', 'g'), ('h<3>', 'i'), ('h<5>', 'l'),
             ('i', 'h<5>')]
        self.assertEqual(sorted(shrink_dsp.dmap.node), r)
        self.assertEqual(sorted(shrink_dsp.dmap.edges()), w)


class TestRemoveCycles(unittest.TestCase):
    def setUp(self):
        dsp = Dispatcher()

        def average(kwargs):
            return sum(kwargs.values()) / len(kwargs)

        dsp.add_data(data_id='b', default_value=3)
        dsp.add_data(data_id='c', function=average)
        dsp.add_function('max', function=max, inputs=['a', 'b'], outputs=['c'])
        dsp.add_function('min', function=min, inputs=['a', 'c'], outputs=['d'])
        dsp.add_function('min', function=min, inputs=['b', 'd'], outputs=['c'])
        dsp.add_function('max', function=max, inputs=['b', 'd'], outputs=['a'])
        self.dsp = dsp

    def test_remove_cycles(self):
        dsp = self.dsp
        # no cycles
        dsp_woc = dsp.remove_cycles(['a', 'b'])
        self.assertEqual(sorted(dsp_woc.dmap.edges()), sorted(dsp.dmap.edges()))

        dsp.nodes['c']['wait_inputs'] = True
        dsp_woc = dsp.remove_cycles(['a', 'b'])
        res = [('a', 'max'), ('a', 'min'), ('b', 'max'), ('b', 'max<0>'),
               ('c', 'min'), ('d', 'max<0>'), ('max', 'c'), ('max<0>', 'a'),
               ('min', 'd')]
        self.assertEqual(sorted(dsp_woc.dmap.edges()), res)
        self.assertTrue(dsp_woc.dmap.node['c']['wait_inputs'])
        self.assertTrue(dsp.dmap.node['c']['wait_inputs'])

        dsp_woc = dsp.remove_cycles(['d', 'b'])
        res = [('a', 'max'), ('a', 'min'), ('b', 'max'), ('b', 'max<0>'),
               ('c', 'min'), ('d', 'max<0>'), ('max', 'c'), ('max<0>', 'a'),
               ('min', 'd')]
        self.assertEqual(sorted(dsp_woc.dmap.edges()), res)

        dsp.dmap.remove_node('max<0>')
        dsp_woc = dsp.remove_cycles(['b', 'd'])
        self.assertEqual(dsp_woc.dmap.edges(), [])

        dsp_woc = dsp.remove_cycles(['a', 'b', 'c'])
        res = [('a', 'max'), ('a', 'min'), ('b', 'max'), ('c', 'min'),
               ('max', 'c'), ('min', 'd')]
        self.assertEqual(sorted(dsp_woc.dmap.edges()), res)