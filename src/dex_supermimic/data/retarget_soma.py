"""Compatibility entry: BONES-SEED SOMA Uniform → bundled v7 at 50 Hz."""
import argparse
from pathlib import Path
import warnings
from .retarget import convert as convert_v7


def convert(source, output, warm_frames=None):
    if warm_frames is not None:
        warnings.warn('v7 uses sequence solving; warm_frames is ignored (no GMR priming).',
                      DeprecationWarning, stacklevel=2)
    convert_v7(source, output, dataset='bones_seed', fps=50.)
    return Path(output)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input'); p.add_argument('--output', required=True)
    p.add_argument('--warm-frames', type=int, default=None)
    a = p.parse_args(); convert(a.input, a.output, a.warm_frames)
