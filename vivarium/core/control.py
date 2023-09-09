"""
===================
Experiment Control
===================

Run experiments and analyses from the command line.
"""

import os
import argparse
import copy

# typing
from typing import (
    Any, Dict, Optional, Union, Sequence, List)
from vivarium.core.types import OutputDict

from vivarium.core.engine import timestamp
from vivarium.core.directories import BASE_OUT_DIR
from vivarium.composites.toys import ToyCompartment, run_composer

from vivarium.plots.simulation_output import plot_simulation_output


def make_dir(out_dir: str = 'out') -> None:
    os.makedirs(out_dir, exist_ok=True)  # pragma: no cover


class Control:
    """ Control experiments from the command line

    Load experiments, plots, and workflows in this Control class,
    and trigger them from the command line
    """

    def __init__(
            self,
            out_dir: Optional[str] = None,
            experiments: Optional[Dict[str, Any]] = None,
            composers: Optional[Dict[str, Any]] = None,
            plots: Optional[Dict[str, Any]] = None,
            workflows: Optional[Dict[str, Any]] = None,
            args: Optional[Sequence[str]] = None,
    ) -> None:
        workflows = workflows or {}
        experiments = experiments or {}
        plots = plots or {}
        workflows = workflows or {}

        self.experiments_library = experiments
        self.compposers_library = composers
        self.plots_library = plots
        self.workflows_library = workflows
        self.output_data = None

        # base output directory
        self.out_dir = BASE_OUT_DIR
        if out_dir:
            self.out_dir = out_dir

        # arguments
        self.args = self.parse_args(args)

        if self.args.experiment:
            experiment_id = str(self.args.experiment)
            self.output_data = self.run_experiment(experiment_id)

        if self.args.workflow:
            workflow_id = str(self.args.workflow)
            self.run_workflow(workflow_id)

    def parse_args(
            self, args: Optional[Sequence[str]] = None
    ) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description='command line control of experiments'
        )
        parser.add_argument(
            '--workflow', '-w',
            type=str,
            choices=list(self.workflows_library.keys()),
            help='the workflow id'
        )
        parser.add_argument(
            '--experiment', '-e',
            type=str,
            choices=list(self.experiments_library.keys()),
            help='experiment id to run'
        )
        return parser.parse_args(args)

    def run_experiment(
            self,
            experiment_config: Union[str, dict]
    ) -> OutputDict:

        if isinstance(experiment_config, dict):
            if 'experiment_id' in experiment_config:
                experiment_id = experiment_config.pop('experiment_id')
                experiment = self.experiments_library[experiment_id]
            else:
                experiment = experiment_config.pop('experiment')
            return experiment(**experiment_config)

        if isinstance(experiment_config, str):
            experiment = self.experiments_library[experiment_config]
            if isinstance(experiment, dict):
                experiment = experiment.pop('experiment')
            return experiment()

        raise ValueError(f'invalid experiment config: {experiment_config}')

    def run_one_plot(
            self,
            plot_config: Union[str, dict],
            data: OutputDict,
            out_dir: Optional[str] = None,
    ) -> None:
        data_copy = copy.deepcopy(data)

        if isinstance(plot_config, str):
            plot_config = self.plots_library[plot_config]

        if isinstance(plot_config, dict):
            if 'plot_id' in plot_config:
                plot_id = plot_config.pop('plot_id')
                plot = self.plots_library[plot_id]
            else:
                plot = plot_config.pop('plot')
            plot(
                data=data_copy,
                out_dir=out_dir,
                **plot_config)

        elif callable(plot_config):
            # call plot directly
            plot_config(
                data=data_copy,
                out_dir=out_dir)
        else:
            raise ValueError(f'invalid plot config: {plot_config}')

    def run_plots(
            self,
            plot_ids: Union[list, str],
            data: OutputDict,
            out_dir: Optional[str] = None,
    ) -> None:

        if isinstance(plot_ids, list):
            for plot_id in plot_ids:
                self.run_one_plot(plot_id, data, out_dir=out_dir)
        else:
            self.run_one_plot(plot_ids, data, out_dir=out_dir)

    def run_workflow(self, workflow_id: str) -> None:
        workflow = self.workflows_library[workflow_id]
        experiment_id = workflow['experiment']
        plot_ids = workflow.get('plots')

        # output directory for this workflow
        workflow_name = workflow.get('name', timestamp())
        out_dir = os.path.join(self.out_dir, workflow_name)

        # run the experiment
        self.output_data = self.run_experiment(experiment_id)

        # run the plots
        if plot_ids:
            self.run_plots(plot_ids, self.output_data, out_dir=out_dir)
            print('plots saved to directory: {}'.format(out_dir))


# testing

def toy_plot(
        data: OutputDict,
        config: Optional[Dict] = None,
        out_dir: Optional[str] = 'out'
) -> None:
    del config  # unused
    plot_simulation_output(data, out_dir=out_dir)


def toy_control(
        args: Optional[Sequence[str]] = None) -> Control:
    """ a toy example of control

    To run:
    > python vivarium/core/control.py -w 1
    """
    experiment_library = {
        # put in dictionary with name
        '1': {
            'name': 'exp_1',
            'experiment': run_composer},
        # map to function to run as is
        '2': run_composer,
    }
    plot_library = {
        # put in dictionary with config
        '1': {
            'plot': toy_plot,
            'config': {}},
        # map to function to run as is
        '2': toy_plot
    }
    composers_library = {
        'agent': ToyCompartment,
    }
    workflow_library = {
        '1': {
            'name': 'test_workflow',
            'experiment': '1',
            'plots': ['1']},
        '2': {
            'name': 'test_workflow',
            'experiment': '1',
            'plots': '2'}
    }

    control = Control(
        out_dir=os.path.join('out', 'control_test'),
        experiments=experiment_library,
        composers=composers_library,
        plots=plot_library,
        workflows=workflow_library,
        args=args,
    )

    return control


def is_float(element: Any) -> bool:
    try:
        float(element)
        return True
    except ValueError:
        return False


def _parse_options(
        options_list: Optional[List[str]]
) -> Dict[str, Union[int, float, bool, str]]:
    """Parse the KEY=VALUE or KEY=k=v option strings into a dict."""
    assignments = options_list or []
    pairs = [
        a.split('=', 1) + [''] for a in assignments
    ]  # [''] to handle the no-'=' case
    options = {}
    for p in pairs:
        key: str = p[0]
        str_value: str = p[1]
        value: Any = None
        if str_value.isdigit():
            value = int(str_value)
        elif is_float(str_value):
            value = float(str_value)
        elif str_value in ['True', 'False']:
            value = bool(str_value)
        else:
            value = str_value
        options[key] = value
    return options


def run_library_cli(library: dict, args: Optional[list] = None) -> None:
    """Run experiments from the command line

    Args:
        library (dict): maps experiment id to experiment function
    """
    parser = argparse.ArgumentParser(
        description='run experiments from the command line')
    parser.add_argument(
        '--name', '-n', default=[], nargs='+',
        help='experiment ids to run')
    parser.add_argument(
        '--options', '-o', metavar='OPTION_KEY=VALUE',
        action='append', help='A "KEY=VALUE" option')
    parser_args = parser.parse_args(args)
    run_all = not parser_args.name
    options = _parse_options(parser_args.options)

    for name in parser_args.name:
        library[name](**options)
    if run_all:
        for name, test in library.items():
            test()


def test_library_cli() -> None:
    def run_fun(key: Any = False) -> dict:
        return {'key': key}
    lib = {'1': run_fun}
    run_library_cli(lib, args=['-n', '1', '-o', 'key=True'])
    run_library_cli(lib, args=['-n', '1', '-o', 'key=0.2'])
    run_library_cli(lib, args=['-n', '1', '-o', 'key=b'])


def test_control() -> None:
    toy_control(args=['-w', '1'])
    toy_control(args=['-w', '2'])
    control = toy_control(args=['-e', '2'])
    control.run_workflow('1')


fun_lib = {
    '0': test_library_cli,
    '1': test_control,
}


# python vivarium/core/control.py -n [test number]
if __name__ == '__main__':
    run_library_cli(fun_lib)
