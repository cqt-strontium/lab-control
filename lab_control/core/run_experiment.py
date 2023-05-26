from .target import Target, TargetMeta
from .action import Action, ActionMeta
import asyncio
import importlib.util
from .util.ts import save_sequences, merge_seq
import typing
from typing import Dict


def all_target_types() -> typing.Generator[TargetMeta, None, None]:
    """ Generator for all types that are subclassed from Target """
    for cls in TargetMeta.instances:
        yield cls


def all_target_instances() -> typing.Generator[Target, None, None]:
    """ Generator for all instances of type subclassed from Target """
    for cls in all_target_types():
        for tar in cls.instances:
            yield tar


def all_tar_act_pairs():
    for tar in all_target_instances():
        for act_t in type(tar).supported_actions:
            if act_t is None:
                continue
            for act in act_t.instances:
                yield tar, act


def list_actions():
    """ Shows supported action types for each target type """
    for cls in all_target_types():
        print(cls.__name__, ':', ', '.join(map(str, cls.supported_actions)))


def get_action_usage(act: ActionMeta):
    """ Displays details of actions types """
    print('>- Action name:', act.__name__)
    print('>- Parent target type:', ActionMeta.targets[act.__name__])
    code = act.__init__.__code__
    print('>- Arguments:')
    if code.co_argcount > 1:
        print('>--- Normal argument(s):', end=' ')
        print(', '.join(code.co_varnames[1:code.co_argcount]))
    if code.co_posonlyargcount > 0:
        print('>--- Positional only argument(s):', end=' ')
        print(
            ', '.join(code.co_varnames[code.co_argcount:][:code.co_posonlyargcount]))
    if code.co_kwonlyargcount > 0:
        print('>--- Keyword only argument(s):', end=' ')
        print(', '.join(
            code.co_varnames[code.co_argcount+code.co_posonlyargcount:][:code.co_kwonlyargcount]))
    print('>- Doc string:', act.__init__.__doc__)


def to_action(s: str) -> ActionMeta:
    """ Convert string to the corresponding action type"""
    if s in ActionMeta.instances:
        return ActionMeta.instances[s]


def list_targets():
    """ Shows all target types """
    for cls in all_target_types():
        print(cls.__name__, ':', ', '.join(map(str, cls.instances)))


async def wait_until_ready():
    await asyncio.gather(*[
        tar.wait_until_ready()
        for tar in all_target_instances()])


def test_precondition():
    return all(tar.test_precondition()
               for tar in all_target_instances())


async def run_preprocess():
    await asyncio.gather(*[
        tar.run_preprocess()
        for tar in all_target_instances()])


def test_postcondition():
    return all(tar.test_postcondition()
               for tar in all_target_instances())


async def run_postprocess():
    await asyncio.gather(*[
        tar.run_postprocess()
        for tar in all_target_instances()])


def cleanup():
    print('[INFO] cleanup')
    for tar in all_target_instances():
        for act in tar.actions.keys():
            act.cleanup()
        tar.cleanup()


def check_channel_clash(*to_seq):
    s = set()
    for seq in to_seq:
        for k in seq.keys():
            if k not in s:
                s.add(k)
            else:
                raise ValueError(
                    "Incompatible channel assignment! Same time sequencer channel is assigned to different targets!")


def prepare_sequencer_files():
    to_seq = tuple(tar.to_time_sequencer()
                   for tar in all_target_instances())
    check_channel_clash(*to_seq)
    exp_time = save_sequences(merge_seq(*to_seq), '1')
    print('[INFO] Time sequencer CSV and OUT file saved.')
    return exp_time


async def run_sequence(fpga, exp_time: int):
    fpga.backend.main('out')
    await asyncio.sleep(exp_time * 1e-6 + .5)


async def run_exp(module_fname: str, **exp_param):
    """ Run an experiment from file. The file is dynamically loaded. """
    spec = importlib.util.find_spec("lab_control.experiments."+module_fname)
    if spec is None:
        raise FileNotFoundError(
            f"Cannot find experiment {module_fname}. Did you forgot to \n1. put it under experiments folder;\n2. use period (e.g. play.exp) instead of slash (e.g. play/exp) to delimit the path?")
    exp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exp)

    if 'main' not in exp.__dict__:
        raise AttributeError(
            f"Cannot find function main() from experiment {module_fname}. Did you forgot to define one?")
    main = exp.main(**exp_param)

    if not isinstance(main, typing.Coroutine):
        raise TypeError(
            f"Cannot execute main() from experiment {module_fname}. Did you forgot to wrap it with Experiment?")
    await main
