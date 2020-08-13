
import sys
import yaml
import os
import time
from datetime import datetime
from termcolor import colored
import re
import subprocess
from patch import Patch

class Batch:

    def __init__(self):
        pass

    def ts(self):
        timestamp = time.time()
        dt = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        return dt

    def local_exec(self,cmd):
        ouput = subprocess.Popen([cmd],
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        error = ouput.stderr.read().decode('utf-8')
        result = ouput.stdout.read().decode('utf-8')
        return result,error

    def snooze(self,host,mode):
        snooze_list = f'snooze list -h {host}'
        snooze_add = f'snooze add -h {host} -d 8h -r "Kernel Patching" -f'
        if mode == 'add':
            result,error = self.local_exec(snooze_add)
        elif mode == 'list':
            result,error = self.local_exec(snooze_list)
        return result,error


    def batch_patch(self,host):
        yes = True
        status = False
        start = time.time()
        obj = Patch(host,True)
        if 'box.net' not in str(host):
            print(colored("Please add your FQDN as an argument e.g. # python3 patch.py jm-data3154.lv7.box.net [-y]",'red'))
            sys.exit(2)
        else:
            state = False
            obj = Patch(str(host),yes)
            obj.log(f' {host} Start Script','info','batch.log')
            print(f'\n\n###############{host}###############\n')
            print(f'{self.ts()}  [INFO] {host}: Started')
            obj.log(f' {host} Checking Sensu status','info','batch.log')
            print(f'{self.ts()}  [INFO] {host} Checking Sensu status')
            result,error = self.snooze(host,'list')
            if not error:
                if 'No matching entries found.' in result:
                    print(f'{self.ts()}  [INFO] {host} Snooze the host')
                    obj.log(f' {host} Snooze the host','info','batch.log')
                    result,error = self.snooze(host,'add')
                    if 'INFO: Sensu silence entry created successfully' in error or 'INFO: Sensu silence entry created successfully' in result:
                        obj.log(f' {host} Snooze added to Sensu','info','batch.log')
                        print(f'{self.ts()}  [INFO] {host} Snooze added to Sensu')
                        state = True
                elif 'kernel patching' not in result.lower() and 'No matching entries found.' not in result :
                    obj.log(f' {host} This host has been silent, might be decommission or under maintenance ','crt','batch.log')
                    obj.log(f' {host} This host needs manual patching','crt','batch.log')
                    print(colored(f"{host} has been silent, might be decommission or under maintenance",'red'))
                    print(colored(f"{host} needs manual patching",'white', 'on_red',['bold','blink']))
                    sys.exit(2)
                elif 'kernel patching' in result:
                    obj.log(f' {host} Host already snoozed for Kernel Patching','info','batch.log')
                    print(f'{self.ts()}  [INFO] {host} already snoozed for Kernel Patching')
                    state = True
        obj.log(f' {host} Waiting till host be silent in Sensu','info','batch.log')
        print(f'{self.ts()}  [INFO] {host} Waiting till host be silent in Sensu')
        while True:
            result,error = self.snooze(host,'list')
            if 'No matching entries found.' in result:
                continue
            else:
                state = True
                obj.log(f' {host} Host snoozed and ready for Kernel Patching','info','batch.log')
                print(f'{self.ts()}  [INFO] {host}  snoozed and ready for Kernel Patching')
                break
        if state:
            status = obj.patch()

        end = time.time()
        total = end - start

        if state and status:
            obj.log(f' {host} Patching finished','info','batch.log')
            if total > 60:
                total = int(total/60)
                print(colored(f'###Execution time is {total} Minutes for {host}###','white', 'on_blue',['bold','blink']))
                obj.log(f' {host} Patching finished','info','batch.log')
                obj.log(f' {host} Execution time is {total} Minutes','info','batch.log')
            else:
                print(colored(f'###Execution time is {int(total)} seconds for {host}###','white', 'on_blue',['bold','blink']))
                obj.log(f' {host} Execution time is {total} seconds','info','batch.log')
            del obj
            return True
        else:
            obj.log(f' {host} Patching failed','crt','batch.log')
            if total > 60:
                total = int(total/60)
                print(colored(f'###Execution time is {total} Minutes for {host}###','white', 'on_red',['bold','blink']))
                obj.log(f' {host} Execution time is {total} Minutes','info','batch.log')
            else:
                print(colored(f'###Execution time is {int(total)} seconds for {host}###','white', 'on_red',['bold','blink']))
                obj.log(f' {host}Execution time is {total} seconds','info','batch.log')
            del obj
            return False
