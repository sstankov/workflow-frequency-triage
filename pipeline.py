#!/usr/bin/env python3
import argparse
from workflow_triage.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description='Analyze CSV → agent review → dist dashboard and CSVs')
    sub = parser.add_subparsers(dest='command',required=True)
    run = sub.add_parser('run',help='Clean and rebuild dist; invoke Codex for step 2')
    run.add_argument('--skip-agent',action='store_true',help='Build incomplete UNKNOWN results for local development')
    run.add_argument('--timeout',type=int,default=600,help='Agent timeout in seconds')
    serve = sub.add_parser('serve',help='Serve the dashboard and persist human corrections')
    serve.add_argument('--port',type=int,default=8765)
    args = parser.parse_args()
    if args.command == 'run':
        return run_pipeline(args.skip_agent,args.timeout)
    from workflow_triage.server import serve_dashboard
    serve_dashboard(args.port)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
