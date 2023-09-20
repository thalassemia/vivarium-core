
import collections.abc
import copy
from functools import reduce
import operator
import traceback
from typing import Optional, Any, Callable
import warnings

import numpy as np
from vivarium.library.units import Quantity


MULTI_UPDATE_KEY = '_multi_update'

tuple_separator = '___'


def merge_dicts(dicts):
    merge = {}
    for d in dicts:
        merge.update(d)
    return merge


def deep_compare(dct_1, dct_2, path=tuple()):
    """Recursively checks for equality between two dictionaries in a way
    that supports Numpy arrays.

    Args:
        dct_1, dct_2, dictionaries to compare
        path: If ``dct_1`` or ``dct_2`` are nested within larger dictionaries,
            this is the path to them. This is normally an empty tuple
            for the end user but is used for recursive calls
    
    Returns:
        True when two dictionaries are equal, False otherwise
    
    Raises:
        ValueError: Raised when conflicting values are found between
            ``dct_1`` and ``dct_2``
    """
    key_diff = dct_1.keys() ^ dct_2.keys()
    if len(key_diff) > 0:
        warnings.warn(f'Unshared keys at {path}: {key_diff}')
        return False
    for key, val_1 in dct_1.items():
        val_2 = dct_2[key]
        if isinstance(val_1, dict) and isinstance(val_2, dict):
            if not deep_compare(val_1, val_2, path + (key,)):
                return False
        elif isinstance(val_1, np.ndarray) and isinstance(val_2, np.ndarray):
            if not np.array_equal(val_1, val_2):
                warnings.warn(f'Dicts differ at {path}: {val_1}, {val_2}')
                return False
        else:
            if not val_1 == val_2:
                warnings.warn(f'Dicts differ at {path}: {val_1}, {val_2}')
                return False
    return True


def deep_merge_check(dct, merge_dct, check_equality=False, path=tuple()):
    """Recursively merge dictionaries with checks to avoid overwriting.

    Args:
        dct: The dictionary to merge into. This dictionary is mutated
            and ends up being the merged dictionary.  If you want to
            keep dct you could call it like
            ``deep_merge_check(copy.deepcopy(dct), merge_dct)``.
        merge_dct: The dictionary to merge into ``dct``.
        check_equality: Whether to use ``==`` to check for conflicts
            instead of the default ``is`` comparator. Note that ``==``
            can cause problems when used with Numpy arrays.
        path: If the ``dct`` is nested within a larger dictionary, the
            path to ``dct``. This is normally an empty tuple (the
            default) for the end user but is used for recursive calls.

    Returns:
        ``dct``

    Raises:
        ValueError: Raised when conflicting values are found between
            ``dct`` and ``merge_dct``.
    """
    for k in merge_dct:
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], collections.abc.Mapping)):
            deep_merge_check(dct[k], merge_dct[k], check_equality, path + (k,))
        elif k in dct and not check_equality and (dct[k] is not merge_dct[k]):
            raise ValueError(
                f'Failure to deep-merge dictionaries at path {path + (k,)}: '
                f'{dct[k]} IS NOT {merge_dct[k]}'
            )
        elif k in dct and check_equality and (dct[k] != merge_dct[k]):
            raise ValueError(
                f'Failure to deep-merge dictionaries at path {path + (k,)}: '
                f'{dct[k]} DOES NOT EQUAL {merge_dct[k]}'
            )
        else:
            dct[k] = merge_dct[k]
    return dct


def deep_merge_combine_lists(dct, merge_dct):
    """ Recursive dict merge with lists

    Values that are lists are combined into one list without repeating values.
    This mutates dct - the contents of merge_dct are added to dct (which is also returned).
    If you want to keep dct you could call it like deep_merge_combine_lists(copy.deepcopy(dct), merge_dct)
    """
    for k, v in merge_dct.items():
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], collections.abc.Mapping)):
            deep_merge_combine_lists(dct[k], merge_dct[k])
        elif k in dct and isinstance(dct[k], list) and isinstance(v, list):
            for i in v:
                if i not in dct[k]:
                    dct[k].append(i)
        else:
            dct[k] = merge_dct[k]
    return dct


def deep_merge_multi_update(dct, merge_dct):
    """ Recursive dict merge combines multiple values

    If a value already exists for a key, it is added in a list
    """
    if dct is None:
        dct = {}
    if merge_dct is None:
        merge_dct = {}
    for k, v in merge_dct.items():
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], collections.abc.Mapping)):
            deep_merge_multi_update(dct[k], merge_dct[k])
        elif k in dct:
            # put values together in a list under '_multi_update' key
            if isinstance(dct[k], dict) and MULTI_UPDATE_KEY in dct[k]:
                dct[k]['_multi_update'].append(merge_dct[k])
            else:
                dct[k] = {
                    '_multi_update': [
                        dct[k], merge_dct[k]]}
        else:
            dct[k] = merge_dct[k]
    return dct


def remove_multi_update(d):
    new = {}
    for k, v in d.items():
        if isinstance(v, dict):
            if '_multi_update' in v:
                new[k] = v['_multi_update'][0]
            else:
                new[k] = remove_multi_update(v)
        else:
            new[k] = v
    return new


def deep_merge(dct, merge_dct):
    """ Recursive dict merge

    This mutates dct - the contents of merge_dct are added to dct (which is also returned).
    If you want to keep dct you could call it like deep_merge(copy.deepcopy(dct), merge_dct)
    """
    if dct is None:
        dct = {}
    if merge_dct is None:
        merge_dct = {}
    for k, v in merge_dct.items():
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], collections.abc.Mapping)):
            deep_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]
    return dct


def deep_copy_internal(d):
    if not isinstance(d, dict):
        return d
    return {
        key: deep_copy_internal(val)
        for key, val in d.items()
    }


def flatten_port_dicts(dicts):
    """
    Input:
        dicts (dict): embedded state dictionaries with the {'port_id': {'state_id': state_value}}

    Return:
        dict: flattened dictionary with {'state_id_port_id': value}
    """
    merge = {}
    for port, states_dict in dicts.items():
        for state, value in states_dict.items():
            merge.update({state + '_' + port: value})
    return merge


def tuplify_port_dicts(dicts):
    """
    Input:
        dicts (dict): embedded state dictionaries with the {'port_id': {'state_id': state_value}}

    Return:
        dict: tuplified dictionary with {(port_id','state_id'): value}
    """
    merge = {}
    for port, states_dict in dicts.items():
        if states_dict:
            for state, value in states_dict.items():
                merge.update({(port, state): value})
    return merge


def flatten_timeseries(timeseries):
    """Flatten a timeseries in the style of flatten_port_dicts"""
    flat = {}
    for port, store_dict in timeseries.items():
        if port == 'time':
            flat[port] = timeseries[port]
            continue
        for variable_name, values in store_dict.items():
            key = "{}_{}".format(port, variable_name)
            flat[key] = values
    return flat


def tuple_to_str_keys(dictionary):
    """
    take a dict with tuple keys, and convert them to strings with tuple_separator as a delimiter
    """
    new_dict = copy.deepcopy(dictionary)
    make_str_dict(new_dict)
    return new_dict


def make_str_dict(dictionary):
    # get down to the leaves first
    for k, v in dictionary.items():
        if isinstance(v, dict):
            make_str_dict(v)

        # convert tuples in lists
        if isinstance(v, list):
            for idx, var in enumerate(v):
                if isinstance(var, tuple):
                    v[idx] = tuple_separator.join(var)
                if isinstance(var, dict):
                    make_str_dict(var)

    # which keys are tuples?
    tuple_ks = [k for k in dictionary.keys() if isinstance(k, tuple)]
    for tuple_k in tuple_ks:
        str_k = tuple_separator.join(tuple_k)
        dictionary[str_k] = dictionary[tuple_k]
        del dictionary[tuple_k]

    return dictionary


def str_to_tuple_keys(dictionary):
    """
    Take a dict with keys that have tuple_separator, and convert them to tuples
    """

    # get down to the leaves first
    for k, v in dictionary.items():
        if isinstance(v, dict):
            str_to_tuple_keys(v)

        # convert strings in lists
        if isinstance(v, list):
            for idx, var in enumerate(v):
                if isinstance(var, str) and tuple_separator in var:
                    v[idx] = tuple(var.split(tuple_separator))
                if isinstance(var, dict):
                    str_to_tuple_keys(var)

    # which keys are tuples?
    str_ks = [k for k in dictionary.keys() if isinstance(k, str) and tuple_separator in k]
    for str_k in str_ks:
        tuple_k = tuple(str_k.split(tuple_separator))
        dictionary[tuple_k] = dictionary[str_k]
        del dictionary[str_k]

    return dictionary


def keys_list(d: dict) -> list:
    """Return list(d.keys())."""
    return list(d.keys())


def value_in_embedded_dict(
        data: dict,
        timeseries: Optional[dict] = None,
        time_index: Optional[float] = None) -> dict:
    """
    converts data from a single time step into an embedded dictionary with lists
    of values.
    If the value has a unit, saves under a key with (key, unit_string).
    """
    # TODO(jerry): ^^^ Explain this further. Note that this function modifies
    #  timeseries.
    # TODO(jerry): Refine the type declarations.
    # TODO(jerry): Use dictionary.setdefault(key, default) to simplify.
    timeseries = timeseries or {}

    for key, value in data.items():
        if isinstance(value, dict):
            if key not in timeseries:
                timeseries[key] = {}
            timeseries[key] = value_in_embedded_dict(value, timeseries[key], time_index)
        elif time_index is None:
            if isinstance(value, Quantity):
                unit_key = (key, str(value.units))
                if unit_key not in timeseries:
                    timeseries[unit_key] = []
                timeseries[unit_key].append(value.magnitude)
            else:
                if key not in timeseries:
                    timeseries[key] = []
                timeseries[key].append(value)
        else:
            if key not in timeseries:
                timeseries[key] = {
                    'value': [],
                    'time_index': []
                }
            timeseries[key]['value'].append(value)
            timeseries[key]['time_index'].append(time_index)

    return timeseries


def get_path_list_from_dict(dictionary):
    paths_list = []
    for key, value in dictionary.items():
        if isinstance(value, dict):
            subpaths = get_path_list_from_dict(value)
            for subpath in subpaths:
                path = (key,) + subpath
                paths_list.append(path)
        else:
            path = (key,)
            paths_list.append(path)
    return paths_list


def get_value_from_path(dictionary, path):
    # noinspection PyBroadException
    try:
        return reduce(operator.getitem, path, dictionary)
    except Exception:
        traceback.print_exc()
        return None


def make_path_dict(embedded_dict):
    """ converts embedded_dict to a flat dict with path names as keys """
    path_dict = {}
    paths_list = get_path_list_from_dict(embedded_dict)
    for path in paths_list:
        path_dict[path] = get_value_from_path(embedded_dict, path)
    return path_dict


def apply_func_to_leaves(root: Any, func: Callable[[Any], None]) -> None:
    '''Apply a function to every leaf node in a nested dictionary.

    >>> root = {1: [], 2: {3: [], 4: []}}
    >>> func = lambda x: x.append(True)
    >>> apply_func_to_leaves(root, func)
    >>> root
    {1: [True], 2: {3: [True], 4: [True]}}
    '''
    if not isinstance(root, dict):
        func(root)
        return
    for child in root.values():
        apply_func_to_leaves(child, func)


def test_deep_copy_internal():
    l = [1, 2, 3]
    d = {1: {2: l}, 3: True}
    copy = deep_copy_internal(d)
    assert copy == d
    assert copy is not d
    assert copy[1] is not d[1]
    assert copy[1][2] is d[1][2]
