#!/usr/bin/env python3
# coding=utf-8

import app
import argparse


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Starts bot processing loop')
    parser.add_argument('identifiers', nargs='+',
                        help='list of bot identifiers')
    parser.add_argument('--no-loop', action='store_true',
                        help='do processing once and exit')

    args = parser.parse_args()

    a = app.App()

    for identifier in args.identifiers:
        a.add_bot(identifier)

    if args.no_loop:
        a.process_bots()
    else:
        a.process_loop()

