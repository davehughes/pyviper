import argparse
import sys

import pyviper.core


def run_sample(opts):
    if opts.verbose:
        print("Processing...")
    print("OK!")
    return 0


def square(x):
    return x * x


def create_argument_parser():
    parser = argparse.ArgumentParser(description='Sample CLI tool')
    subparsers = parser.add_subparsers()

    cmd_sample = subparsers.add_parser('test')
    cmd_sample.add_argument('-v', '--verbose',
                            action='store_true',
                            )
    cmd_sample.set_defaults(func=run_sample)

    return parser


def main(args=None):
    args = args or sys.argv[1:]
    parser = create_argument_parser()
    config = pyviper.core.Config(parser)
    opts = config.parse_args(args)
    return opts.func(opts)


if __name__ == '__main__':
    main()
