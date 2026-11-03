"""Small dispatcher: runtime/ROS environments need not import the training stack."""
import argparse
import importlib
import runpy
import sys

COMMANDS = {
    'data': 'data.prepare',
    'train': 'training.train',
    'bundle': 'deployment.build_bundle',
    'play': 'deployment.native_mujoco',
    'ros': 'deployment.run_ros_isolated',
    'evaluate': 'evaluation.evaluate',
    'watch': 'evaluation.worker',
    'video': 'evaluation.render',
    'check': 'check',
}

def main():
    p = argparse.ArgumentParser(description='Dex SuperMimic: data → train → bundle → play/ROS → evaluate/video')
    p.add_argument('command', choices=COMMANDS)
    a = p.parse_args(sys.argv[1:2])
    rest = sys.argv[2:]
    sys.argv = ['dex-sm ' + a.command] + rest
    module = 'dex_supermimic.' + COMMANDS[a.command]
    if a.command == 'data':
        # ProcessPool workers must have an importable module-qualified identity.
        importlib.import_module(module).main()
    else:
        runpy.run_module(module, run_name='__main__')

if __name__ == '__main__':
    main()
