from datetime import datetime
import re
import urllib3
from argparse import ArgumentParser
import logging
import multiprocessing as mp


def main():
    status = False
    start = time.time()
    yes = False
    parser =ArgumentParser(description='HBase data node patching automation',
            epilog='Enjoy the program! :)')

    parser.add_argument('--host',help='Just Run the scipt on one host')
    parser.add_argument('--file','-f',help='accept host file and run one node per cluster')
    parser.add_argument('--cluster','-c',help='accept host file and run one node per cluster')
    parser.add_argument('--yes','-y',action="store_true", default=False,help='Skip all confirmation question and execute the script')
    args = parser.parse_args()
    if args.yes:
        yes = True
    else:
        print(colored(f'###Please watch the script it will ask you questions otherwise choose -y or --yes','yellow', 'on_blue',['bold','blink']))
    if args.host and not args.file:
        if 'box.net' not in str(args.host):
            print(colored("Please add your FQDN as an argument e.g. # python3 patch.py jm-data3154.lv7.box.net [-y]",'red'))
        else:
            host = args.host
            obj = Patch(str(args.host),yes)
            status = obj.patch()


    if args.file and not args.host:
        procs=[]
        yes = True
        file = args.file
        if os.path.exists(file):
            with open(file) as f:
                hosts = f.readlines()
            for host in hosts:
                host = host.strip()
                # obj = Patch(host,yes)
                # procs.append(mp.Process(target=obj.patch))
                # for proc in procs:
                #     proc.start()

    end = time.time()
    total = end - start
    if total > 60:
        total = int(total/60)
        print(colored(f'###Execution time is {total} Minutes for {host}###','white', 'on_blue',['bold','blink']))
    else:
        print(colored(f'###Execution time is {int(total)} seconds for {host}###','white', 'on_blue',['bold','blink']))



if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted")
