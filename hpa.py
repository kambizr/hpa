#!/home/kambizrahmani//pyenv/bin/python
import sys
import yaml
import os
import time
from datetime import datetime
from termcolor import colored
import re
import urllib3
import subprocess
from argparse import ArgumentParser
from patch import Patch
from batch import Batch


def ts():
    timestamp = time.time()
    dt = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    return dt

def local_exec(cmd):
    ouput = subprocess.Popen([cmd],
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
    error = ouput.stderr.read().decode('utf-8')
    result = ouput.stdout.read().decode('utf-8')
    return result,error

def snooze(host,mode):
    snooze_list = f'snooze list -h {host}'
    snooze_add = f'snooze add -h {host} -d 8h -r "Kernel Patching" -f'
    if mode == 'add':
        result,error = local_exec(snooze_add)
    elif mode == 'list':
        result,error = local_exec(snooze_list)
    return result,error

def yaml_conf(file='conf.yaml'):
    f = open(file)
    conf = yaml.load(f,Loader=yaml.FullLoader)
    f.close()
    return conf

def main():
    status = False
    start = time.time()
    yes = False
    parser =ArgumentParser(description='HBase data node patching automation',
            epilog='Enjoy the program! :)')

    parser.add_argument('--host',help='Just Run the scipt on one host')
    parser.add_argument('--file','-f',help='accept host file and run one node per cluster')
    parser.add_argument('--yes','-y',action="store_true", default=False,help='Skip all confirmation question and execute the script')
    args = parser.parse_args()

#single host patching
    if args.host and not args.file:
        if args.yes:
            yes = True
        else:
            print(colored(f'WARNING: Please watch the script it will ask you questions otherwise choose -y or --yes','red', 'on_yellow',['bold','blink']))

        if 'box.net' not in str(args.host):
            print(colored("Please add your FQDN as an argument e.g. # python3 patch.py jm-data3154.lv7.box.net [-y]",'red'))
            sys.exit(2)
        else:
            state = False
            host = args.host
            obj = Patch(str(args.host),yes)
            obj.log(f'Start Script','info')
            print(f'\n\n###############{host}###############\n')
            print(f'{ts()}  [INFO] {host}: Started')
            obj.log(f'Checking Sensu status','info')
            print(f'{ts()}  [INFO] {host} Checking Sensu status')
            result,error = snooze(host,'list')
            if not error:
                if 'No matching entries found.' in result:
                    print(f'{ts()}  [INFO] {host} Snooze the host')
                    obj.log(f'Snooze the host','info')
                    result,error = snooze(host,'add')
                    if 'INFO: Sensu silence entry created successfully' in error or 'INFO: Sensu silence entry created successfully' in result:
                        obj.log(f'Snooze added to Sensu','info')
                        print(f'{ts()}  [INFO] {host} Snooze added to Sensu')
                        state = True
                elif 'kernel patching' not in result.lower() and 'No matching entries found.' not in result :
                    obj.log(f'This host has been silent, might be decommission or under maintenance ','crt')
                    obj.log(f'This host needs manual patching','crt')
                    print(colored(f"{host} has been silent, might be decommission or under maintenance",'red'))
                    print(colored(f"{host} needs manual patching",'white', 'on_red',['bold','blink']))
                    sys.exit(2)
                elif 'kernel patching' in result:
                    obj.log(f'Host already snoozed for Kernel Patching','info')
                    print(f'{ts()}  [INFO] {host} already snoozed for Kernel Patching')
                    state = True
        obj.log(f'Waiting till host be silent in Sensu','info')
        print(f'{ts()}  [INFO] {host} Waiting till host be silent in Sensu')
        while True:
            result,error = snooze(host,'list')
            if 'No matching entries found.' in result:
                continue
            else:
                state = True
                obj.log(f'Host snoozed and ready for Kernel Patching','info')
                print(f'{ts()}  [INFO] {host}  snoozed and ready for Kernel Patching')
                break
        if state:
            status = obj.patch()

        end = time.time()
        total = end - start

        if state and status:
            if total > 60:
                total = int(total/60)
                print(colored(f'###Execution time is {total} Minutes for {host}###','white', 'on_blue',['bold','blink']))
                obj.log(f'Execution time is {total} Minutes','info')
            else:
                print(colored(f'###Execution time is {int(total)} seconds for {host}###','white', 'on_blue',['bold','blink']))
                obj.log(f'Execution time is {total} seconds','info')
        else:
            if total > 60:
                total = int(total/60)
                print(colored(f'###Execution time is {total} Minutes for {host}###','white', 'on_red',['bold','blink']))
                obj.log(f'Execution time is {total} Minutes','info')
            else:
                print(colored(f'###Execution time is {int(total)} seconds for {host}###','white', 'on_red',['bold','blink']))
                obj.log(f'Execution time is {total} seconds','info')


#accept host file and patch one node per cluster
    elif args.file and not args.host:
        data={}
        hosts= []
        obj_batch = Batch()
        yes = True
        file = args.file
        pattern_host = re.compile(r'')
        if os.path.exists(file):
            with open(file) as f:
                hosts_tmp = f.readlines()
        else:
            print(colored(f"{args.file} Dose not exist, check your path or filenema",'red'))
            sys.exit(2)
        #snooze all hosts and wait for snooze
        for item in hosts_tmp:
            hosts.append(item.strip())

        for host in hosts:
            obj_batch = Batch()
            status = obj_batch.batch_patch(host)
            if not status:
                print(colored(f'{host} Failed ','white', 'on_red',['bold','blink']))
                sys.exit(2)
            else:
                del obj_batch








if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted")
