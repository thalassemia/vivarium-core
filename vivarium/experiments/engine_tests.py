import random
import logging as log
from typing import Optional, Union, Dict, Any, cast, List

from vivarium.composites.toys import (
    PoQo, Sine, ToyDivider, ToyTransport, ToyEnvironment, ToyProcess,
    Proton, Electron, MoveProcess)
from vivarium.core.composer import Composer, Composite
from vivarium.core.engine import Engine, pf, pp, _StepGraph
from vivarium.core.process import Process, Step, Deriver
from vivarium.core.store import Store, hierarchy_depth
from vivarium.core.types import (
    Schema, State, Update, Topology, Steps, Processes)
from vivarium.library.units import units
from vivarium.library.wrappers import make_logging_process
from vivarium.core.control import run_library_cli


def _make_proton(
        parallel: bool = False
) -> Dict[str, Any]:
    processes = {
        'proton': Proton({'_parallel': parallel}),
        'electrons': {
            'a': {
                'electron': Electron({'_parallel': parallel})},
            'b': {
                'electron': Electron()}}}

    spin_path = ('internal', 'spin')
    radius_path = ('structure', 'radius')

    topology = {
        'proton': {
            'radius': radius_path,
            'quarks': ('internal', 'quarks'),
            'electrons': {
                '_path': ('electrons',),
                '*': {
                    'orbital': ('shell', 'orbital'),
                    'spin': spin_path}}},
        'electrons': {
            'a': {
                'electron': {
                    'spin': spin_path,
                    'proton': {
                        '_path': ('..', '..'),
                        'radius': radius_path}}},
            'b': {
                'electron': {
                    'spin': spin_path,
                    'proton': {
                        '_path': ('..', '..'),
                        'radius': radius_path}}}}}

    initial_state = {
        'structure': {
            'radius': 0.7},
        'internal': {
            'quarks': {
                'x': {
                    'color': 'green',
                    'spin': 'up'},
                'y': {
                    'color': 'red',
                    'spin': 'up'},
                'z': {
                    'color': 'blue',
                    'spin': 'down'}}}}

    return {
        'processes': processes,
        'topology': topology,
        'initial_state': initial_state}


def test_recursive_store() -> None:
    environment_config = {
        'environment': {
            'temperature': {
                '_default': 0.0,
                '_updater': 'accumulate'},
            'fields': {
                (0, 1): {
                    'enzymeX': {
                        '_default': 0.0,
                        '_updater': 'set'},
                    'enzymeY': {
                        '_default': 0.0,
                        '_updater': 'set'}},
                (0, 2): {
                    'enzymeX': {
                        '_default': 0.0,
                        '_updater': 'set'},
                    'enzymeY': {
                        '_default': 0.0,
                        '_updater': 'set'}}},
            'agents': {
                '1': {
                    'location': {
                        '_default': (0, 0),
                        '_updater': 'set'},
                    'boundary': {
                        'external': {
                            '_default': 0.0,
                            '_updater': 'set'},
                        'internal': {
                            '_default': 0.0,
                            '_updater': 'set'}},
                    'transcripts': {
                        'flhDC': {
                            '_default': 0,
                            '_updater': 'accumulate'},
                        'fliA': {
                            '_default': 0,
                            '_updater': 'accumulate'}},
                    'proteins': {
                        'ribosome': {
                            '_default': 0,
                            '_updater': 'set'},
                        'flagella': {
                            '_default': 0,
                            '_updater': 'accumulate'}}},
                '2': {
                    'location': {
                        '_default': (0, 0),
                        '_updater': 'set'},
                    'boundary': {
                        'external': {
                            '_default': 0.0,
                            '_updater': 'set'},
                        'internal': {
                            '_default': 0.0,
                            '_updater': 'set'}},
                    'transcripts': {
                        'flhDC': {
                            '_default': 0,
                            '_updater': 'accumulate'},
                        'fliA': {
                            '_default': 0,
                            '_updater': 'accumulate'}},
                    'proteins': {
                        'ribosome': {
                            '_default': 0,
                            '_updater': 'set'},
                        'flagella': {
                            '_default': 0,
                            '_updater': 'accumulate'}}}}}}

    state = Store(environment_config)
    state.apply_update({})
    state.state_for(['environment'], ['temperature'])


def test_topology_ports() -> None:
    proton = _make_proton()

    experiment = Engine(**proton)

    log.debug(pf(experiment.state.get_config(True)))

    experiment.update(10.0)

    log.debug(pf(experiment.state.get_config(True)))
    log.debug(pf(experiment.state.divide_value()))


def test_timescales() -> None:
    class Slow(Process):
        name = 'slow'
        defaults = {'timestep': 3.0}

        def __init__(self, config: Optional[dict] = None) -> None:
            super().__init__(config)

        def ports_schema(self) -> Schema:
            return {
                'state': {
                    'base': {
                        '_default': 1.0}}}

        def next_update(
                self,
                timestep: Union[float, int],
                states: State) -> Update:
            base = states['state']['base']
            next_base = timestep * base * 0.1

            return {
                'state': {'base': next_base}}

    class Fast(Process):
        name = 'fast'
        defaults = {'timestep': 0.3}

        def __init__(self, config: Optional[dict] = None) -> None:
            super().__init__(config)

        def ports_schema(self) -> Schema:
            return {
                'state': {
                    'base': {
                        '_default': 1.0},
                    'motion': {
                        '_default': 0.0}}}

        def next_update(
                self,
                timestep: Union[float, int],
                states: State) -> Update:
            base = states['state']['base']
            motion = timestep * base * 0.001

            return {
                'state': {'motion': motion}}

    processes = {
        'slow': Slow(),
        'fast': Fast()}

    states = {
        'state': {
            'base': 1.0,
            'motion': 0.0}}

    topology: Topology = {
        'slow': {'state': ('state',)},
        'fast': {'state': ('state',)}}

    emitter = {'type': 'null'}
    experiment = Engine(
        processes=processes,
        topology=topology,
        emitter=emitter,
        initial_state=states)

    experiment.update(10.0)


def test_2_store_1_port() -> None:
    """
    Split one port of a processes into two stores
    """

    class OnePort(Process):
        name = 'one_port'

        def ports_schema(self) -> Schema:
            return {
                'A': {
                    'a': {
                        '_default': 0,
                        '_emit': True},
                    'b': {
                        '_default': 0,
                        '_emit': True}
                }
            }

        def next_update(
                self,
                timestep: Union[float, int],
                states: State) -> Update:
            return {
                'A': {
                    'a': 1,
                    'b': 2}}

    class SplitPort(Composer):
        """splits OnePort's ports into two stores"""
        name = 'split_port_composer'

        def generate_processes(
                self, config: Optional[dict]) -> Dict[str, Any]:
            return {
                'one_port': OnePort({})}

        def generate_topology(self, config: Optional[dict]) -> Topology:
            return {
                'one_port': {
                    'A': {
                        'a': ('internal', 'a',),
                        'b': ('external', 'a',)
                    }
                }}

    # run experiment
    split_port = SplitPort({})
    network = split_port.generate()
    exp = Engine(**{
        'processes': network['processes'],
        'topology': network['topology']})

    exp.update(2)
    output = exp.emitter.get_timeseries()
    expected_output = {
        'external': {'a': [0, 2, 4]},
        'internal': {'a': [0, 1, 2]},
        'time': [0.0, 1.0, 2.0]}
    assert output == expected_output


class MultiPort(Process):
    name = 'multi_port'

    def ports_schema(self) -> Schema:
        return {
            'A': {
                'a': {
                    '_default': 0,
                    '_emit': True}},
            'B': {
                'a': {
                    '_default': 0,
                    '_emit': True}},
            'C': {
                'a': {
                    '_default': 0,
                    '_emit': True}}}

    def next_update(
            self,
            timestep: Union[float, int],
            states: State) -> Update:
        return {
            'A': {'a': 1},
            'B': {'a': 1},
            'C': {'a': 1}}


class MergePort(Composer):
    """combines both of MultiPort's ports into one store"""
    name = 'multi_port_composer'

    def generate_processes(
            self, config: Optional[dict]) -> Dict[str, Any]:
        return {
            'multi_port': MultiPort({})}

    def generate_topology(self, config: Optional[dict]) -> Topology:
        return {
            'multi_port': {
                'A': ('aaa',),
                'B': ('aaa',),
                'C': ('aaa',)}}


def test_multi_port_merge() -> None:
    # run experiment
    merge_port = MergePort({})
    network = merge_port.generate()
    exp = Engine(**{
        'processes': network['processes'],
        'topology': network['topology']})

    exp.update(2)
    output = exp.emitter.get_timeseries()
    expected_output = {
        'aaa': {'a': [0, 3, 6]},
        'time': [0.0, 1.0, 2.0]}

    assert output == expected_output


def test_emit_config() -> None:
    # test alternate emit options
    merge_port = MergePort({})
    network = merge_port.generate()
    exp1 = Engine(
        processes=network['processes'],
        topology=network['topology'],
        emit_topology=False,
        emit_processes=True,
        emit_config=True,
        progress_bar=True,
        emit_step=2,
    )

    exp1.update(10)


def test_complex_topology() -> None:
    # make the experiment
    outer_path = ('universe', 'agent')
    pq = PoQo({})
    pq_composite = pq.generate(path=outer_path)
    pq_composite.pop('_schema')
    experiment = Engine(composite=pq_composite)

    # get the initial state
    initial_state = experiment.state.get_value()
    print('time 0:')
    pp(initial_state)

    # simulate for 1 second
    experiment.update(1)

    next_state = experiment.state.get_value()
    print('time 1:')
    pp(next_state)

    # pull out the agent state
    initial_agent_state = initial_state['universe']['agent']
    agent_state = next_state['universe']['agent']

    assert agent_state['aaa']['a1'] == initial_agent_state['aaa']['a1'] + 1
    assert agent_state['aaa']['x'] == initial_agent_state['aaa']['x'] - 9
    assert agent_state['ccc']['a3'] == initial_agent_state['ccc']['a3'] + 1


def test_parallel() -> None:
    proton = _make_proton(parallel=True)
    experiment = Engine(**proton)

    log.debug(pf(experiment.state.get_config(True)))

    experiment.update(10.0)

    log.debug(pf(experiment.state.get_config(True)))
    log.debug(pf(experiment.state.divide_value()))

    experiment.end()


def test_depth() -> None:
    nested = {
        'A': {
            'AA': 5,
            'AB': {
                'ABC': 11}},
        'B': {
            'BA': 6}}

    dissected = hierarchy_depth(nested)
    assert len(dissected) == 3
    assert dissected[('A', 'AB', 'ABC')] == 11


def test_sine() -> None:
    sine = Sine()
    print(sine.next_update(0.25 / 440.0, {
        'frequency': 440.0,
        'amplitude': 0.1,
        'phase': 1.5}))


def test_units() -> None:
    class UnitsMicrometer(Process):
        name = 'units_micrometer'

        def ports_schema(self) -> Schema:
            return {
                'A': {
                    'a': {
                        '_default': 0 * units.um,
                        '_emit': True},
                    'b': {
                        '_default': 'string b',
                        '_emit': True,
                    },
                    'c': {
                        '_default': 0,
                        '_emit': True,
                    }
                }
            }

        def next_update(
                self, timestep: Union[float, int], states: State) -> Update:
            return {
                'A': {
                    'a': 1 * units.um,
                    'c': 1,
                }}

    class UnitsMillimeter(Process):
        name = 'units_millimeter'

        def ports_schema(self) -> Schema:
            return {
                'A': {
                    'a': {
                        # '_default': 0 * units.mm,
                        '_emit': True}}}

        def next_update(
                self, timestep: Union[float, int], states: State) -> Update:
            return {
                'A': {'a': 1 * units.mm}}

    class MultiUnits(Composer):
        name = 'multi_units_composer'

        def generate_processes(
                self,
                config: Optional[dict]) -> Dict[str, Any]:
            return {
                'units_micrometer':
                    UnitsMicrometer({}),
                'units_millimeter':
                    UnitsMillimeter({})}

        def generate_topology(self, config: Optional[dict]) -> Topology:
            return {
                'units_micrometer': {
                    'A': ('aaa',)},
                'units_millimeter': {
                    'A': ('aaa',)}}

    # run experiment
    multi_unit = MultiUnits({})
    network = multi_unit.generate()
    exp = Engine(**{
        'processes': network['processes'],
        'topology': network['topology']})

    exp.update(5)
    timeseries = exp.emitter.get_timeseries()
    print('TIMESERIES')
    pp(timeseries)

    data = exp.emitter.get_data()
    print('DATA')
    pp(data)

    data_deserialized = exp.emitter.get_data_deserialized()
    print('DESERIALIZED')
    pp(data_deserialized)

    data_unitless = exp.emitter.get_data_unitless()
    print('UNITLESS')
    pp(data_unitless)

    query = [('aaa', 'a'), ('aaa', 'c')]
    query_data = exp.emitter.get_data(query)
    print('QUERY DATA')
    pp(query_data)


def test_custom_divider() -> None:
    """ToyDividerProcess has a custom `split_divider`"""
    agent_id = '1'
    composer = ToyDivider({
        'agent_id': agent_id,
        'divider': {
            'x_division_threshold': 3,
        }
    })
    composite = composer.generate(path=('agents', agent_id))

    experiment = Engine(
        processes=composite.processes,
        steps=composite.steps,
        flow=composite.flow,
        topology=composite.topology,
    )

    experiment.update(8)
    data = experiment.emitter.get_data()

    expected_data = {
        0.0: {'agents': {'1': {'variable': {'x': 0, '2x': 0}}}},
        1.0: {'agents': {'1': {'variable': {'x': 1, '2x': 2}}}},
        2.0: {'agents': {'1': {'variable': {'x': 2, '2x': 4}}}},
        3.0: {'agents': {'1': {'variable': {'x': 3, '2x': 6}}}},
        4.0: {'agents': {'1': {'variable': {'x': 4, '2x': 8}}}},
        5.0: {'agents': {'10': {'variable': {'x': 2, '2x': 4}},
                         '11': {'variable': {'x': 2, '2x': 4}}}},
        6.0: {'agents': {'10': {'variable': {'x': 3, '2x': 6}},
                         '11': {'variable': {'x': 3, '2x': 6}}}},
        7.0: {'agents': {'10': {'variable': {'x': 4, '2x': 8}},
                         '11': {'variable': {'x': 4, '2x': 8}}}},
        8.0: {'agents': {'100': {'variable': {'x': 2, '2x': 4}},
                         '101': {'variable': {'x': 2, '2x': 4}},
                         '110': {'variable': {'x': 2, '2x': 4}},
                         '111': {'variable': {'x': 2, '2x': 4}}}}
    }
    assert data == expected_data


class TestStepGraph:

    @staticmethod
    def test_step_graph_execution_layers() -> None:
        tg = _StepGraph()
        tg.add(('a',), [])
        tg.add(('b',), [])
        tg.add(('c',), [('a',), ('b',)])
        tg.add(('d',), [('c',)])

        layers = list(tg.get_execution_layers())
        expected_layers = [
            [('a',), ('b',)],
            [('c',)],
            [('d',)],
        ]
        assert layers == expected_layers

    @staticmethod
    def test_step_graph_sequential() -> None:
        tg = _StepGraph()
        tg.add(('a',), [])
        tg.add(('b',), [])
        tg.add_sequential(('c',))

        layers = list(tg.get_execution_layers())
        expected_layers = [
            [('c',)],
            [('a',), ('b',)],
        ]
        assert layers == expected_layers

    @staticmethod
    def test_step_graph_removal() -> None:
        tg = _StepGraph()
        tg.add(('a',), [])
        tg.add(('b',), [('a',)])
        tg.add(('c',), [('b',)])

        tg.remove(('a',))
        layers = list(tg.get_execution_layers())

        assert not layers


def test_runtime_order() -> None:
    class RuntimeOrderProcess(Process):

        def ports_schema(self) -> Schema:
            return {
                'store': {
                    'var': {
                        '_default': 0
                    }
                }
            }

        def next_update(self, timestep: float, states: State) -> Update:
            _ = states
            self.parameters['execution_log'].append(self.name)
            return {}

    class RuntimeOrderStep(Step):

        def ports_schema(self) -> Schema:
            return {
                'store': {
                    'var': {
                        '_default': 0
                    }
                }
            }

        def next_update(self, timestep: float, states: State) -> Update:
            _ = states
            self.parameters['execution_log'].append(self.name)
            return {}

    class RuntimeOrderDeriver(Deriver):

        def ports_schema(self) -> Schema:
            return {
                'store': {
                    'var': {
                        '_default': 0
                    }
                }
            }

        def next_update(self, timestep: float, states: State) -> Update:
            _ = states
            self.parameters['execution_log'].append(self.name)
            return {}

    class RuntimeOrderComposer(Composer):

        def generate_processes(
                self, config: Optional[dict]) -> Dict[str, Any]:
            config = cast(dict, config or {})
            proc1 = RuntimeOrderProcess({
                'name': 'process1',
                'time_step': 1,
                'execution_log': config['execution_log'],
            })
            proc2 = RuntimeOrderProcess({
                'name': 'process2',
                'time_step': 2,
                'execution_log': config['execution_log'],
            })
            deriver = RuntimeOrderDeriver({
                'name': 'deriver',
                'execution_log': config['execution_log'],
            })
            return {
                'p1': proc1,
                'p2': proc2,
                'd': deriver,
            }

        def generate_steps(self, config: Optional[dict]) -> Steps:
            config = config or {}
            step1 = RuntimeOrderStep({
                'name': 'step1',
                'execution_log': config['execution_log'],
            })
            step2 = RuntimeOrderStep({
                'name': 'step2',
                'execution_log': config['execution_log'],
            })
            step3 = RuntimeOrderStep({
                'name': 'step3',
                'execution_log': config['execution_log'],
            })
            return {
                's1': step1,
                's2': step2,
                's3': step3,
            }

        def generate_flow(self, config: Optional[dict]) -> Steps:
            config = config or {}
            return {
                's1': [],
                's2': [('s1',)],
                's3': [('s1',)],
            }

        def generate_topology(self, config: Optional[dict]) -> Topology:
            return {
                'p1': {
                    'store': ('store',),
                },
                'p2': {
                    'store': ('store',),
                },
                'd': {
                    'store': ('store',),
                },
                's1': {
                    'store': ('store',),
                },
                's2': {
                    'store': ('store',),
                },
                's3': {
                    'store': ('store',),
                },
            }

    execution_log: List[str] = []
    composer = RuntimeOrderComposer()
    composite = composer.generate({'execution_log': execution_log})
    experiment = Engine(
        processes=composite.processes,
        steps=composite.steps,
        flow=composite.flow,
        topology=composite.topology,
    )
    experiment.update(4)
    expected_log = [
        ('deriver', 'step1'),
        {'step2', 'step3'},
        {'process1', 'process2'},
        ('deriver', 'step1'),
        {'step2', 'step3'},
        {'process1'},
        ('deriver', 'step1'),
        {'step2', 'step3'},
        {'process1', 'process2'},
        ('deriver', 'step1'),
        {'step2', 'step3'},
        {'process1'},
        ('deriver', 'step1'),
        {'step2', 'step3'},
    ]
    for expected_group in expected_log:
        num = len(expected_group)
        group = execution_log[0:num]
        execution_log = execution_log[num:]
        if isinstance(expected_group, tuple):
            assert tuple(group) == expected_group
        elif isinstance(expected_group, set):
            assert set(group) == expected_group


def get_toy_transport_in_env_composite(
        agent_id: Any = '0',
        transport_config: Optional[dict] = None,
        environment_config: Optional[dict] = None,
) -> Composite:
    processes = {
        'agents': {
            agent_id: {
                'transport': ToyTransport(transport_config)}},
        'environment': ToyEnvironment(environment_config)}
    topology = {
        'environment': {
            'agents': {
                '_path': ('agents',),
                '*': {
                    'external': ('external', 'GLC')}}},
        'agents': {
            agent_id: {
                'transport': {
                    'internal': ('internal',),
                    'external': ('external',)}}}}
    return Composite({
        'processes': processes,
        'topology': topology,
    })


def test_glob_schema() -> None:
    composite = get_toy_transport_in_env_composite()
    experiment = Engine(
        processes=composite.processes,
        topology=composite.topology)
    experiment.update(10)

    # declare processes in reverse order
    processes_reverse = {
        'environment': ToyEnvironment(),
        'agents': {'0': {'transport': ToyTransport()}}}

    experiment_reverse = Engine(
        processes=processes_reverse,
        topology=composite.topology)
    experiment_reverse.update(10)


def get_env_view_composite(agent_id: Any = '1') -> Composite:
    agent_composer = ToyDivider({
        'agent_id': agent_id,
        'divider': {
            'x_division_threshold': 3,
        }
    })
    composite = agent_composer.generate(path=('agents', agent_id))

    environment_process = {
        'environment': make_logging_process(ToyEnvironment)()
    }
    environment_topology: Topology = {
        'environment': {
            'agents': {
                '_path': ('agents',),
                '*': {
                    'external': ('external', 'GLC')
                }
            },
            'log_update': ('log_update',),
        }
    }

    # combine the environment and agent
    composite.merge(
        processes=environment_process,
        topology=environment_topology,
    )
    return composite


def test_environment_view_with_division() -> None:
    composite = get_env_view_composite()
    experiment = Engine(
        processes=composite.processes,
        topology=composite.topology)
    experiment.update(10)
    data = experiment.emitter.get_data()

    # confirm that the environment sees the new agents.
    once_different = False
    for state in data.values():
        agent_ids = set(state['agents'].keys())
        env_agents = set(state['log_update'].get('agents', {}).keys())
        if env_agents != agent_ids:
            if not once_different:
                once_different = True
            else:
                # the values have been different for more than one update
                raise ValueError(
                    f'environment sees {env_agents} instead of {agent_ids}')
        else:
            once_different = False


class AddDelete(Process):
    def ports_schema(self) -> Schema:
        return {
            'sub_stores': {
                '*': {
                    '_default': 0,
                    '_emit': True
                }
            },
            'expected': {
                '_default': [],
                '_updater': 'set',
            }
        }

    def next_update(
            self, timestep: Union[float, int], states: State) -> Update:
        sub_stores = set(states['sub_stores'].keys())
        expected = set(states['expected'])
        assert sub_stores == expected, "stores don't match expected"

        # delete current stores, and add the same number of stores
        sub_stores_update: dict = {
            '_delete': [],
            '_add': []}
        new_sub_stores = []
        for store_id in sub_stores:
            sub_stores_update['_delete'].append(store_id)
            new_id = str(random.randint(0, 2 ** 63))
            new_sub_stores.append(new_id)
            new_store = {'key': new_id, 'state': 1}
            sub_stores_update['_add'].append(new_store)

        return {
            'sub_stores': sub_stores_update,
            'expected': new_sub_stores,
        }


def test_add_delete() -> None:
    process = AddDelete()
    topology = {
        'sub_stores': ('sub_stores',),
        'expected': ('expected',)}

    # initial state
    n_initial = 10
    initial_substores = [
        str(random.randint(0, 2**63)) for _ in range(n_initial)]
    initial_state = {
        'sub_stores': {
            sub_store: 1
            for sub_store in initial_substores
        },
        'expected': initial_substores,
    }

    experiment = Engine(
        processes={'process': process},
        topology={'process': topology},
        initial_state=initial_state,
    )
    experiment.update(10)

    # assert that no overlapping sub store between time steps.
    # All sub stores should get deleted, and new sub stores added
    data = experiment.emitter.get_data()
    times = list(data.keys())
    n_times = len(times)
    for t_index in range(n_times):
        if t_index < n_times - 1:
            current_time = times[t_index]
            next_time = times[t_index + 1]
            current_ids = set(data[current_time]['sub_stores'].keys())
            next_ids = set(data[next_time]['sub_stores'].keys())
            assert len(set(current_ids).intersection(set(next_ids))) == 0


def test_hyperdivision(profile: bool = True) -> None:
    total_time = 10
    n_agents = 100
    division_thresholds = [3, 4, 5, 6, 7]  # what values of x triggers division?

    # initialize agent composer
    agent_composer = ToyDivider()

    # make the composite
    composite = Composite()
    agent_ids = [str(agent_idx) for agent_idx in range(n_agents)]
    for agent_id in agent_ids:
        divider_config = {
            'divider': {
                    'x_division_threshold': random.choice(division_thresholds),
                }}
        agent_composite = agent_composer.generate(
            config={
                'agent_id': agent_id,
                **divider_config,
            },
            path=('agents', agent_id))
        composite.merge(agent_composite)

    # add an environment
    environment_process: Processes = {'environment': ToyEnvironment()}
    environment_topology: Topology = {
        'environment': {
            'agents': {
                '_path': ('agents',),
                '*': {
                    'external': ('external', 'GLC')
                }
            },
        }
    }

    # combine the environment and agent
    composite.merge(
        processes=environment_process,
        topology=environment_topology,
    )

    # make the sim, run the sim, retrieve the data
    experiment = Engine(
        processes=composite.processes,
        steps=composite.steps,
        flow=composite.flow,
        topology=composite.topology,
        profile=profile,
    )
    experiment.update(total_time)
    experiment.end()
    data = experiment.emitter.get_data()

    print(f"n agents initial: {n_agents}")
    print(f"n agents final: {len(data[total_time]['agents'].keys())}")
    assert len(data[total_time]['agents'].keys()) > n_agents

    if profile:
        stats = experiment.stats
        stats.strip_dirs().sort_stats(  # type: ignore
            'cumulative', 'cumtime').print_stats(20)

        # make sure view_values is fast
        stats_view_values = stats.get_print_list(  # type: ignore
            ('view_values',))[1]
        view_values_times = stats.stats[  # type: ignore
            stats_view_values[0]][3]
        total_runtime = stats.total_tt  # type: ignore
        assert view_values_times < 0.1 * total_runtime

def test_output_port() -> None:
    a_default = 1
    b_default = 2

    class InputOutput(Process):
        def ports_schema(self) -> Schema:
            return {
                'input': {
                    'A': {
                        '_default': a_default,
                        '_emit': True,
                    }
                },
                'output': {
                    '_output': True,
                    'B': {
                        '_default': b_default,
                        '_emit': True,
                    }
                }
            }
        def next_update(
                self,
                timestep: Union[float, int],
                states: State) -> Update:
            assert not states['output'], 'outputs should be masked'
            return {}

    total_time = 10
    composite = InputOutput().generate()
    sim = Engine(
        processes=composite['processes'],
        topology=composite['topology']
    )
    sim.update(total_time)
    data = sim.emitter.get_timeseries()
    assert data['input']['A'] == [a_default for _ in range(total_time + 1)]
    assert data['output']['B'] == [b_default for _ in range(total_time + 1)]


def test_engine_run_for() -> None:
    total_time = 10.0
    time_interval = 1.0
    timestep1 = 0.75
    timestep2 = 1.25

    topo = {
        'external': ('external',),
        'internal': ('internal',),
    }
    composite = Composite({
        'processes': {
            'process1': ToyTransport({'time_step': timestep1}),
            'process2': ToyTransport({'time_step': timestep2}),
        },
        'topology': {
            'process1': topo,
            'process2': topo,
        }
    })
    initial_state = {
        'external': {'GLC': 100},
    }

    sim = Engine(
        processes=composite.processes,
        topology=composite.topology,
        initial_state=initial_state)

    time = 0.0
    while sim.global_time < total_time:
        if time + time_interval >= total_time:
            # If this is the last iteration of the simulation loop,
            # force processes to complete.
            sim.run_for(time_interval, force_complete=True)
        else:
            sim.run_for(time_interval)
        time += time_interval
        assert sim.global_time == time

        # check that the front has advanced correctly
        front = sim.front
        for path, advance in front.items():
            expected_time = 0.0
            if time >= total_time:
                expected_time = total_time
            elif path[0] == 'process1':
                expected_time = int(time / timestep1) * timestep1
            elif path[0] == 'process2':
                expected_time = int(time / timestep2) * timestep2
            assert advance['time'] == expected_time, \
                f"front time {advance['time']} " \
                f"is not expected {expected_time}"

    final_time = time
    assert sim.global_time == final_time

    front = sim.front
    for path, advance in front.items():
        assert advance['time'] == sim.global_time, \
            f"process at path {path} did not complete"


def test_set_branch_emit() -> None:
    run_time = 5
    # get the composer
    composer = PoQo({})

    # turn on emits
    composite = composer.generate()
    exp = Engine(
        composite=composite,
        store_schema={'_emit': True}
    )
    exp.update(run_time)
    data = exp.emitter.get_data()
    assert data[run_time]['bbb'] != {}, 'this emit should be on'
    print(pf(data))

    # turn off emits
    composite = composer.generate()
    exp = Engine(
        composite=composite,
        store_schema={'_emit': False}
    )
    exp.update(run_time)
    data = exp.emitter.get_data()
    assert data[run_time]['bbb'] == {}, 'this emit should be off'
    print(pf(data))

    # selectively turn on emits
    composite = composer.generate()
    exp = Engine(
        composite=composite,
        store_schema={'bbb': {'e2': {'_emit': True}}},
    )
    exp.update(run_time)
    data = exp.emitter.get_data()
    assert data[run_time]['bbb']['e2'] != {}, 'this emit should be on'
    assert data[run_time]['ccc'] == {}, 'this emit should be off'
    print(pf(data))


def test_add_new_state() -> None:
    agent_id = '1'
    composite = get_toy_transport_in_env_composite(agent_id=agent_id)
    new_schema = {
        'agents': {
            agent_id: {
                'extra': {'_emit': True, '_value': 1.0}}}}
    experiment = Engine(
        processes=composite.processes,
        topology=composite.topology,
        store_schema=new_schema,
    )

    assert experiment.state['agents', agent_id, 'extra'].get_value() == 1.0

    total_time = 5
    experiment.update(total_time)
    timeseries = experiment.emitter.get_timeseries()
    assert len(timeseries['agents'][agent_id]['extra']) == total_time + 1


def test_floating_point_timesteps() -> None:
    agent_id = '1'
    transport_timestep = 0.1
    composite = get_toy_transport_in_env_composite(
        agent_id=agent_id,
        transport_config={'time_step': transport_timestep}
    )
    sim = Engine(
        processes=composite.processes,
        topology=composite.topology,
        global_time_precision=5
    )
    sim.update(1)
    data = sim.emitter.get_data()
    print(pf(data))
    for t in data.keys():
        ntimes = round(t / transport_timestep, 5)
        expected_t = round(ntimes * transport_timestep, 5)
        assert t == expected_t, f'bad timestep {t}'


def test_move_update() -> None:
    agents_in_1 = ['a1', 'a2']
    agents_in_2 = ['a3', 'a4']
    agents_in_3 = ['a5', 'a6']

    composite = Composite({
        'processes': {
            'move': MoveProcess({'timestep': 2}),
            'store1': {
                agent_id: {
                    'toy': ToyProcess({'timestep': 1})
                } for agent_id in agents_in_1},
        },
        'topology': {
            'move': {
                '1': ('store1',),
                '2': ('store2',),
                '3': ('store3',),
            },
            'store1': {
                agent_id: {
                    'toy': {
                        'port1': ('store_A',),
                        'port2': ('store_B',)
                    }
                } for agent_id in agents_in_1},
        }})

    state = {
        'store1': {
            agent_id: {
                'store_A': {'var_a': 0.1, 'var_b': 0.2},
                'store_B': {'var_a': 0.3, 'var_b': 0.4},
            } for agent_id in agents_in_1
        },
        'store2': {
            agent_id: {} for agent_id in agents_in_2
        },
        'store3': {
            agent_id: {} for agent_id in agents_in_3
        },
    }

    sim = Engine(
        processes=composite.processes,
        topology=composite.topology,
        initial_state=state,
    )

    sim.update(4)
    data = sim.emitter.get_data()

    # it should move at t=2, t=4
    assert list(data[4]['store1'].keys()) == agents_in_2
    assert list(data[4]['store2'].keys()) == agents_in_3
    assert list(data[4]['store3'].keys()) == agents_in_1
    assert 'var_a' in data[4]['store3'][agents_in_1[0]]['store_A'], \
        'the agent initialized in store1 should have ' \
        'carried its internal states generated by ToyProcess'



engine_tests = {
    '0': test_recursive_store,
    '1': test_topology_ports,
    '2': test_timescales,
    '3': test_2_store_1_port,
    '4': test_multi_port_merge,
    '5': test_emit_config,
    '6': test_complex_topology,
    '7': test_parallel,
    '8': test_depth,
    '9': test_sine,
    '10': test_units,
    '11': test_custom_divider,
    '12': test_runtime_order,
    '13': test_glob_schema,
    '14': test_environment_view_with_division,
    '15': test_add_delete,
    '16': test_hyperdivision,
    '17': test_output_port,
    '18': test_engine_run_for,
    '19': test_set_branch_emit,
    '20': test_add_new_state,
    '21': test_floating_point_timesteps,
    '22': test_move_update,
}


# python vivarium/experiments/engine_tests.py -n [test number]
if __name__ == '__main__':
    run_library_cli(engine_tests)
