import subprocess
import yaml
import time
import sys
import os
from termcolor import colored
from datetime import datetime
import re
import urllib3
from argparse import ArgumentParser
import logging
import multiprocessing as mp
'''
This Script accept hostname and run the following steps:
1.Make snapshot of regions
2. decommisiion the node
3. Verify for decommisiion
4. Install paches
5. reboot
6. verify updates
7. recommision the node
8. verify recommission
9. restore regions
10. run compact_rs
Developed by: Kambiz Rahmani
'''
class Patch:
    def __init__(self,hostname,yes):
        self.hostname = hostname
        self.yes = yes

    def log(self,msg,mode,logfile=None):
        if not logfile:
            logfile = './logs/'+self.hostname+'.log'
        else:
            logfile = './logs/'+logfile
        logging.basicConfig(filename = logfile,
                format='%(asctime)s  [%(levelname)s]  %(message)s',
                datefmt='%m/%d/%Y %I:%M:%S %p',level=logging.INFO)
        if 'info' in mode: logging.info(msg)
        if 'wrn' in mode: logging.warning(msg)
        if 'err' in mode: logging.error(msg)
        if 'crt' in mode: logging.critical(msg)
        if 'dbg' in mode: logging.debug(msg)

    def ts(self):
        timestamp = time.time()
        dt = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        return dt

    def exec(self,cmd):
        sp = subprocess.Popen(["ssh","-o","StrictHostKeyChecking=no",
                "-o","BatchMode=yes","-o", "LogLevel=error",self.hostname,cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        try:
            output,error = sp.communicate(timeout=3600)
        except subprocess.TimeoutExpired:
            sp.kill()
            output,error = proc.communicate()
        result = output.decode('utf-8')
        err = error.decode('utf-8')
        return result,err

    def yaml_conf(self):
        f = open('conf.yaml')
        conf = yaml.load(f,Loader=yaml.FullLoader)
        f.close()
        return conf

    def host_stat(self):
        stat = False
        status,result =  subprocess.getstatusoutput(f"ping -c 1 {self.hostname}")
        if status == 0: stat = True
        return stat

    def local_exec(self,cmd):
        ouput = subprocess.Popen([cmd],
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        error = ouput.stderr.read().decode('utf-8')
        result = ouput.stdout.read().decode('utf-8')
        return result,error


    def reboot(self):
        sp = subprocess.Popen(["ssh","-o","StrictHostKeyChecking=no",
                "-o","BatchMode=yes","-o", "LogLevel=error","%s" % self.hostname,'sudo reboot','now'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        error = sp.stderr.read().decode('utf-8')
        result = sp.stdout.read().decode('utf-8')
        if not error:
            time.sleep(100)
            i = 0
            while not self.host_stat():
                time.sleep(1)
                i += 1
                if i == 1200:
                    print(colored(f"[ERR] {self.hostname} IS NOT BOOTING BACKUP",'red'))
                    self.log('NOT BOOTING BACKUP','crt')
                    return False
            else:
                return True
    def patching(self,key=None):
        config =self.yaml_conf()
        patch_conf = config['patch']
        if not key:
            for package in patch_conf.keys():
                for cmd in patch_conf[package]:
                    result,error =  self.exec(cmd)
                    if not error :
                        print(f'{self.ts()}  [INFO] {self.hostname} {cmd} executed successfully')
                        self.log(f'{cmd} executed successfully','info')
        elif key:
            for cmd in patch_conf[key]:
                result,error =  self.exec(cmd)
                if not error :
                    print(f'{self.ts()}  [INFO] {self.hostname}  {cmd} executed successfully')
                    self.log(f'{cmd} executed successfully','info')




    def validation(self,conf):
        for check in conf:
            result,error = self.exec(conf[check]['cmd'])
            if not error:
                if conf[check]['msg'] not in str(result):
                    print(colored(f'{self.ts()}  [VRF]  {self.hostname} {check} Verified','green'))
                    self.log(f'{check} Verified','info')
                elif conf[check]['msg'] in str(result):
                    print(colored(f'{self.ts()}  [VRF]  {self.hostname} {check} Needs Update try to update it....','red'))
                    self.log(f'{check} Needs Update try to update it','wrn')
                    while True:
                        self.patching(check)
                        result,error = self.exec(conf[check]['cmd'])
                        if conf[check]['msg'] not in str(result):
                            print(colored(f'{self.ts()}  [VRF]  {self.hostname} {check} Verified','green'))
                            self.log(f'{check} Verified','info')
                            break
                        else:
                            print(colored(f'{self.ts()}  [VRF]  {self.hostname} {check} Needs Update try to update it....','red'))
                            self.log(f'{check} Needs Update try to update it','wrn')
                            break
                else:
                    print(f'{self.ts()}  [INFO] {self.hostname} {check} is not installed in this server')
                    self.log(f'{check} is not installed in this server','info')
            else:
                print(colored(f'{self.ts()}  [ERR]  {self.hostname} ERROR: {error}','red'))
                self.log(f'{error}','err')




    def data_locality(self):
        #Delete current snapshots local files
        if os.path.exists(f'./dataLocality/before_activity_{self.hostname}'): os.remove(f'./dataLocality/before_activity_{self.hostname}')
        if os.path.exists(f'./dataLocality/after_activity_{self.hostname}'): os.remove(f'./dataLocality/after_activity_{self.hostname}')
        #find current timestamp and create re pattern
        query1 =f'echo "status \'simple\'" | hbase shell |grep -i {self.hostname}'
        cp_cmd= f'scp {self.hostname}:~/before_activity ./dataLocality/before_activity_{self.hostname}'
        pattern_after =  re.compile(r"(move\s)([a-z0-9',]+\s)([a-z0-9.'-]+\,)([0-9]+,)([0-9]+)(\')",re.IGNORECASE)
        pattern_compact =  re.compile(r"(move\s)([a-z0-9',]+\s)([a-z0-9.'-]+\,)([0-9]+,)([0-9]+)(\')",re.IGNORECASE)
        detailed_node = f'echo "status \'detailed\'"|hbase shell |grep -A3 {self.hostname}'
        #send query
        result,error  = self.exec(query1)
        #get new timestamp
        new_ts = result.split(' ')[-1]
        #copy before_activity file to local
        result,error = self.local_exec(cp_cmd)
        if error:
            print(error)

        with open(f'./dataLocality/before_activity_{self.hostname}','r') as f:
            lines = f.readlines()
        #write after_activity with current timestamp
        for line in lines:
            if self.hostname in line:
                match = re.search(pattern_after,line)
                new_line = str(match.group(1)+match.group(2)+match.group(3)+match.group(4)+str(new_ts).strip()+"'")

                with open(f'./dataLocality/after_activity_{self.hostname}','a+') as l:
                    l.write(new_line+'\n')

        with open(f'./dataLocality/after_activity_{self.hostname}') as after:
            after_lines = after.readline()

        match_compact = re.search(pattern_compact,after_lines)
        compact =  str(match.group(3)+match.group(4)+str(new_ts).strip())

        with open(f'./dataLocality/after_activity_{self.hostname}') as file:
            lines = file.readlines()

        print(f'{self.ts()}  [INFO] {self.hostname} Moving regions in progress...')
        self.log(f'Moving regions in progress','info')

        for line in lines:
            move = query1 =f'echo "{line.strip()}" | hbase shell '
            result,error =  self.exec(move)


        cm1 = 'echo "compact_rs '
        cm2 = ',true"|hbase shell'
        compact_rs = cm1 + f"{compact}'"+cm2
        print(f'{self.ts()}  [INFO] {self.hostname} Executing compact_rs')
        self.log(f'Executing compact_rs','info')
        result,error = self.exec(compact_rs)
        if 'row(s) in' in result:
            print(f'{self.ts()}  [INFO] {self.hostname} Compaction executed sucessfully')
            self.log(f'Compaction executed sucessfully','info')

        pattern_block = re.compile(r'([0-9.]+)')
        rs_stat = ':60030/rs-status'
        http = urllib3.PoolManager()
        url = f'http://{self.hostname}{rs_stat}'
        print(f'{self.ts()}  [INFO] {self.hostname} wait till Block Locality reach 70')
        self.log(f'wait till Block Locality reach 70','info')
        while True:
            r = http.request('GET', url, preload_content=False)
            data_temp =r.data.decode('utf-8')
            data_list = data_temp.split('\n')
            j = 0
            d= []
            for line in data_list:
                if 'block locality' in line.lower():
                    for n in range(0,8):
                        d.append(data_list[j+n])
                j +=1
            match_block = re.search(pattern_block,d[7])
            block_locality =int(float(match_block.group(1)))

            if block_locality < 70:
                time.sleep(60)
            else:
                print(f'{self.ts()}  [INFO] {self.hostname} Block Locality number is {block_locality}')
                self.log(f'Block Locality number is {block_locality}','info')
                break
        return True





    def patch(self):
        #local commands
        decom_cmd = f'/usr/bin/hcm host {self.hostname} -a decommission'
        recom_cmd = f'/usr/bin/hcm host {self.hostname} -a recommission'
        sn_cp = f'scp ~/patch/ToolBox-assembly-0.1.0-SNAPSHOT.jar {self.hostname}:~'
        sn_exe_cp = f'scp ~/patch/run.sh {self.hostname}:~'
        puppet = 'sudo /box/bin/runpuppet -y'
        #read yaml config file
        config = self.yaml_conf()
        status = False
        decom = False
        recom = False
        #################Pre patching####################
        #copy Kevin's script to the node to take snapshot

        #execute Kevin's script to make a snapshot
        print(f'{self.ts()}  [INFO] {self.hostname} Status verifivation')
        self.log(f'Verify Status','info')
        result,error =  self.exec(config['recom_exe']['cmd2']['cmd'])
        if str(config['recom_exe']['cmd2']['msg']).lower() in str(result):
            print(f'{self.ts()}  [INFO] {self.hostname} is in Normal state')
            self.log(f'Host is in Normal state','info')
            status = True
            result,error = self.local_exec(sn_cp)
            if error:
                print(colored(f'{self.ts()}  [ERR] {self.hostname} {error}','red'))
                self.log(f'{error}','err')
            else:
                print(f'{self.ts()}  [INFO] {self.hostname} ToolBox-assembly-0.1.0-SNAPSHOT.jar Copied sucessfully')
                self.log(f'ToolBox-assembly-0.1.0-SNAPSHOT.jar Copied sucessfully','info')
            result,error = self.local_exec(sn_exe_cp)
            if error:
                status = False
                print(colored(f'{self.ts()}  [ERR] {self.hostname} {error}','red'))
                self.log(f'{error}','err')
            else:
                print(f'{self.ts()}  [INFO] {self.hostname} run.sh Copied sucessfully')
                self.log(f'run.sh Copied sucessfully','info')
            result,error = self.exec("sh ~/run.sh")
            if result:
                print(f'{self.ts()}  [INFO] {self.hostname} Snapshot created sucessfully')
                self.log(f'Snapshot created sucessfully','info')
        else:
            result,error = self.exec(config['decom_verify']['cmd'])
            if config['decom_verify']['msg'] in result.lower():
                print(f'{self.ts()}  [INFO] {self.hostname} Host is Decommissioned')
                self.log(f'Host is Decommissioned','info')
                decom = True
                status = True
            else:
                decom = False
                status = False
                print(colored(f'{self.ts()}  [ERR]   {self.hostname} is not ready for patching please manually verify it ','red'))
                self.log(f'is not ready for patching please manually verify it','crt')

        #Decommission the node
        if status and not decom:
            if not self.yes:
                ans = input(f"do you want to decommission {self.hostname}(y/n):")
                if ans.lower() == 'y':
                    staus = True
                else:
                    print(f'{self.ts()}  [INFO] {self.hostname} Can not be patch at this momemnt ')
                    status = False
            if status:
                print(f'{self.ts()}  [INFO] {self.hostname} Decommission in progress')
                self.log(f'Decommission in progress','info')
                i = 1
                while i <= 3:
                    result,error  = self.local_exec(decom_cmd)
                    if '[INFO] SUCCESS! HCM decommissioning process for' in result or '[INFO] SUCCESS! HCM decommissioning process for' in error:
                        print(f'{self.ts()}  [INFO] {self.hostname} Decommission command finished successfully')
                        self.log(f'Decommission command finished successfully','info')
                        decom = True
                        break
                    else:
                        print(colored(f'{self.ts()}  [WRN]  {self.hostname} Retry NO.{i} of 3 to Decommission is failed','yellow'))
                        self.log(f'Retry NO.{i} of 3 to Recommisioning is failed','wrn')
                        i += 1
                if not decom:
                    print(colored(f'{self.ts()}  [ERR]   {self.hostname} Script Exit Because Node could not be decommissioned','red'))
                    self.log(f'Script Exit Because Node could not be decommissioned','crt')
                    status = False


        # #run general prep commands:
        if decom and status:
            prep_srvs = sn_exe = config['all_prep']['service'].keys()
            for srv in prep_srvs:
                cmd = config['all_prep']['service'][srv]['cmd']
                vrf = config['all_prep']['service'][srv]['vrf']
                msg =  config['all_prep']['service'][srv]['msg']
                print(f'{self.ts()}  [INFO] {self.hostname} RUN: {cmd} ')
                self.log(f'RUN: {cmd}','info')
                result,error = self.exec(cmd)
                if error:
                    print(colored(f'{self.ts()}  [ERR]  {self.hostname} Error on {srv}:  {error} ','red'))
                    self.log(f'Error on {srv}:  {error}','err')
                else:
                    result,error = self.exec(vrf)
                    time.sleep(2)
                    if msg in str(result):
                        print(colored(f'{self.ts()}  [VRF]  {self.hostname} {srv} verified for pre Patching','green'))
                        self.log(f'{srv} verified for pre Patching','info')
                    else:
                        print(colored(f'{self.ts()}  [ERR]  {self.hostname} {srv} not verified for Pre-Patching Message:\n {result}','red'))
                        self.log(f'not verified for Pre-Patching Message:\n {result}','err')

            #execute special prep command for specific nodes
            types =  config['node_prep_type']
            for type in types.keys():
                if type in self.hostname:
                    type_cmds = config['node_prep_type'][type].keys()
                    print(colored(f'{self.ts()}  [INFO] {self.hostname} it is {type} node ','cyan'))
                    self.log(f'it is {type} node','info')
                    for cmds in type_cmds:
                        cmd = config['node_prep_type'][type][cmds]['cmd']
                        vrf = config['node_prep_type'][type][cmds]['vrf']
                        msg = config['node_prep_type'][type][cmds]['msg']
                        print(f'{self.ts()}  [INFO] {self.hostname} Run {cmd} ')
                        self.log(f'Run {cmd}','info')
                        result,error = self.exec(cmd)
                        if error:
                            print(colored(f'{self.ts()}  [ERR]  {self.hostname} ERROR on: {cmds}: {error} ','red'))
                            self.log(f' ERROR on: {cmds}: {error}','err')
                        else:
                            result,error = self.exec(vrf)
                            if error:
                                print(colored(f'{self.ts()}  [ERR]  {self.hostname} Verification ERROR on: {cmds}: {error} ','red'))
                                self.log(f'Verification ERROR on: {cmds}: {error}','err')
                            else:
                                if msg in result:
                                    print(colored(f'{self.ts()}  [VRF]  {self.hostname} {cmds} verified for pre Patching','green'))
                                    self.log(f'{cmds} verified for pre Patching','info')
                                else:
                                    print(colored(f'{self.ts()}  [ERR]  {self.hostname} {cmds} not verified for Pre-Patching Message:\n {result}','red'))
                                    self.log(f'{cmds} not verified for Pre-Patching Message:\n {result}','err')

        ####Decomission verification
        if decom and status:
            print(f'{self.ts()}  [INFO] {self.hostname} Don\'t be rush,Decommission still in progress')
            self.log(f'Don\'t be rush,Decommission still in progress','info')
            t =  0
            while True:
                if t == 7200:
                    print(colored(f'{self.ts()}  [ERR]  {self.hostname} Decommission Timeout  ','red'))
                    self.log(f'Decommission Timeout','err')
                    staus = False
                result,error = self.exec(config['decom_verify']['cmd'])
                if config['decom_verify']['msg'] in result.lower():
                    print(colored(f'{self.ts()}  [VFY]  {self.hostname} verified: Decommissioned ','green'))
                    self.log(f'Node verified: Decommissioned','info')
                    status = True
                    break
                else:
                    t =+1
                    time.sleep(1)

            # ######################Patching#######################
            if self.yes and status:
                self.patching()
            else:
                ans = input(f"do you want to patch {self.hostname}(y/n):")
                if ans.lower() == 'y':
                    self.patching()
                else:
                    print(f'{self.ts()}  [INFO] {self.hostname} Can not be patch at this momemnt ')



        ###################Rebooting####################
        if decom and status and self.yes:
            print(colored(f'{self.ts()}  [WRN]  Rebooting {self.hostname}','yellow'))
            self.log(f'rebooting','wrn')
            result = self.reboot()
            if result :
                while True:
                    time.sleep(5)
                    result,error = self.exec('uname -r')
                    if not error:
                        print(f'{self.ts()}  [INFO] {self.hostname} Rebooted successfully')
                        self.log(f'Rebooted successfully','info')
                        break
            else:
                staus = False

        elif decom and status and not self.yes:
            ans = input(f"do you want to reboot {self.hostname}(y/n):")
            if ans.lower() == 'y':
                print(colored(f'{self.ts()}  [WRN]  {self.hostname} Rebooting {self.hostname}','yellow'))
                self.log(f'Rebooting','wrn')
                result = self.reboot()
                if result :
                    while True:
                        time.sleep(5)
                        result,error = self.exec('uname -r')
                        if not error:
                            print(f'{self.ts()}  [INFO] {self.hostname} rebooted successfully')
                            self.log(f'Rebooted successfully','info')
                            break
                else:
                    staus = False

        ####################### Post patching#########################
        #patching validation
        if status and decom:
            self.validation(config['validation'])


        ############recommission the node#######################
        if self.yes and status and decom:
            i = 1
            while i <= 3:
                print(f'{self.ts()}  [INFO] {self.hostname} Recommission in progress')
                self.log(f'Recommission in progress','info')
                result,error  = self.local_exec(recom_cmd)
                if 'SUCCESS! HCM recommissioning process for' in result or 'SUCCESS! HCM recommissioning process for' in error:
                    print(f'{self.ts()}  [INFO] {self.hostname} Recommission command finished successfully')
                    self.log(f'Recommission command finished successfully','info')
                    print(f'{self.ts()}  [INFO] {self.hostname} sleep 2 mins then Run the puppet')
                    self.log(f'sleep 2 mins then Run the puppet','info')
                    time.sleep(120)

                    print(f'{self.ts()}  [INFO] {self.hostname} Puppet is running...')
                    self.log(f'Puppet is running','info')


                    result,error = self.exec(puppet)
                    if error:
                        print(colored(f'{self.ts()}  [ERR] {self.hostname} {error}','red'))
                        self.log(f'{error}','err')
                    else:
                        print(f'{self.ts()}  [INFO] {self.hostname} Puppetrun fnished sucessfully ')
                        self.log(f'Puppetrun fnished sucessfully','info')
                    recom = True
                    break
                else:
                    print(colored(f'{self.ts()}  [WRN]  {self.hostname} Retry NO.{i} of 3 to Recommisioning is failed','yellow'))
                    self.log(f'Retry NO.{i} of 3 to Recommisioning is failed','wrn')
                    i += 1
            if not recom:
                print(colored(f'{self.ts()}  [ERR]   {self.hostname} Script Exit Because Node could not be recommissione','red'))
                self.log(f'Script Exit Because Node could not be recommissione','crt')
                status = False
        elif status and decom and not self.yes:
            ans = input(f"do you want to recommission {self.hostname}(y/n):")
            if ans.lower() == 'y':
                i = 1
                while i <= 3:
                    print(f'{self.ts()}  {self.hostname} [INFO] Recommission in progress')
                    self.log(f'Recommission in progress','info')
                    result,error  = self.local_exec(recom_cmd)
                    if 'SUCCESS! HCM recommissioning process for' in result or 'SUCCESS! HCM recommissioning process for' in error:
                        print(f'{self.ts()}  [INFO] {self.hostname} Recommission command finished successfully')
                        self.log(f'Recommission command finished successfully','info')
                        print(f'{self.ts()}  [INFO] {self.hostname} sleep 2 mins then Run the puppet')
                        self.log(f'sleep 2 mins then Run the puppet','info')
                        time.sleep(120)
                        print(f'{self.ts()}  [INFO] {self.hostname} Puppet is running...')
                        self.log(f'Puppet is running','info')
                        result,error = self.exec(puppet)
                        if error:
                            print(colored(f'{self.ts()}  [ERR] {self.hostname} {error}','red'))
                            self.log(f'{error}','err')
                        result,error = self.exec(puppet)
                        if error:
                            print(colored(f'{self.ts()}  [ERR] {self.hostname} {error}','red'))
                            self.log(f'{error}','err')
                        else:
                            print(f'{self.ts()}  [INFO] {self.hostname} Puppetrun fnished sucessfully ')
                            self.log(f'Puppetrun fnished sucessfully','info')
                        recom = True
                        break
                    else:
                        print(colored(f'{self.ts()}  [WRN]  {self.hostname} Retry NO.{i} of 3 to Recommisioning is failed','yellow'))
                        self.log(f'Retry NO.{i} of 3 to Recommisioning is failed','wrn')
                        i += 1
                if not recom:
                    print(colored(f'{self.ts()}  [ERR]   {self.hostname} Script Exit Because Node could not be decommissioned','red'))
                    self.log(f'Script Exit Because Node could not be recommissione','crt')
                    status = False

        # #Start Services
        if status and recom:
            post_srvs = sn_exe = config['all_post']['service'].keys()
            for srv in post_srvs:
                cmd = config['all_post']['service'][srv]['cmd']
                vrf = config['all_post']['service'][srv]['vrf']
                msg =  config['all_post']['service'][srv]['msg']
                print(f'{self.ts()}  [INFO] {self.hostname} RUN: {cmd} ')
                self.log(f'RUN: {cmd}','info')
                result,error = self.exec(cmd)
                if error:
                    print(colored(f'{self.ts()}  [ERR]  {self.hostname} Error on {srv}:  {error} ','red'))
                    self.log(f'Error on {srv}:  {error}','err')
                else:
                    result,error = self.exec(vrf)
                    time.sleep(2)
                    if msg in str(result):
                        print(colored(f'{self.ts()}  [VRF]  {self.hostname} {srv} verified for Post Patching','green'))
                        self.log(f'{srv} verified for Post Patching','info')
                    else:
                        print(colored(f'{self.ts()}  [ERR]  {self.hostname} {srv} not verified for Post Patching Message:\n {result}','red'))
                        self.log(f'{srv} not verified for Post Patching Message:\n {result}','err')

            types =  config['node_post_type']
            for type in types.keys():
                if type in self.hostname:
                    type_cmds = config['node_post_type'][type].keys()
                    print(colored(f'{self.ts()}  [INFO] {self.hostname} is {type} node ','cyan'))
                    self.log(f'Host is {type} node','info')

                    for cmds in type_cmds:
                        cmd = config['node_post_type'][type][cmds]['cmd']
                        vrf = config['node_post_type'][type][cmds]['vrf']
                        msg = config['node_post_type'][type][cmds]['msg']
                        print(f'{self.ts()}  [INFO] Run {cmd} ')
                        self.log(f'Run {cmd}','info')
                        result,error = self.exec(cmd)
                        if error:
                            print(colored(f'{self.ts()}  [ERR]  {self.hostname} ERROR on: {cmds}: {error} ','red'))
                            self.log(f'ERROR on: {cmds}: {error}','err')
                        else:
                            result,error = self.exec(vrf)
                            if error:
                                print(colored(f'{self.ts()}  [ERR]  {self.hostname} Verification ERROR on: {cmds}: {error} ','red'))
                                self.log(f'Verification ERROR on: {cmds}: {error}','err')
                            else:
                                if msg in result:
                                    print(colored(f'{self.ts()}  [VRF]  {self.hostname} {cmds} verified for post patching','green'))
                                    self.log(f'{cmds} verified for post patching','info')
                                else:
                                    print(colored(f'{self.ts()}  [ERR]  {self.hostname} {cmds} not verified for post patching Message:\n {result}','red'))
                                    self.log(f'{cmds} not verified for post patching Message:\n {result}','info')

            # Recommission verification
            vrf1 = False
            vrf2 = False
            i = 1

            while i <= 3:
                print(f'{self.ts()}  [INFO] {self.hostname} Retry: {i} Recommissioning Verifivation')
                self.log(f'Retry: {i} Recommissioning Verifivation','info')
                if not vrf1:
                    result,error =  self.exec(config['recom_exe']['cmd1']['cmd'])
                    if str(config['recom_exe']['cmd1']['msg']).lower() in str(result):
                        print(colored(f'{self.ts()}  [VRF]  {self.hostname} Recommissioning verified 1 of 2 ','green'))
                        self.log(f'Recommissioning verified 1 of 2','info')
                        vrf1 = True
                    else:
                        print(colored(f'{self.ts()}  [ERR]  {self.hostname} Retry NO.{i} Recommissioning verified 1 of 2 failed ','red'))
                        self.log(f'Retry NO.{i} recommissioning verified 1 of 2 failed','err')
                if not vrf2:
                    result,error =  self.exec(config['recom_exe']['cmd2']['cmd'])
                    if str(config['recom_exe']['cmd2']['msg']).lower() in str(result):
                        vrf2 =  True
                        print(colored(f'{self.ts()}  [VRF]  {self.hostname} Recommissioning verified 2 of 2 ','green'))
                        self.log(f'Recommissioning verified 2 of 2','info')
                    else:
                        print(colored(f'{self.ts()}  [ERR]  {self.hostname} Retry NO.{i} Recommissioning verified 2 of 2 failed ','red'))
                        self.log(f'Retry NO.{i} Recommissioning verified 2 of 2 failed','err')
                if vrf1 and vrf2:
                    print(colored(f'{self.ts()}  [VRF]  {self.hostname} verified: Recommissioned ','green'))
                    self.log(f'verified: Recommissioned','info')
                    break
                i += 1
            if not vrf1 or not vrf2:
                 print(colored(f'{self.ts()}  [ERR]  {self.hostname} script exit because node recommission Failed ','red'))
                 self.log(f'script exit because node recommission Failed','crt')
                 status = False
        if status and recom and self.yes:
            print(f'{self.ts()}  {self.hostname} [INFO] Recommission in progress')
            self.log(f'Recommission in progress','info')
            result,error  = self.local_exec(recom_cmd)
            DataLocality = self.data_locality()
            if DataLocality:
                print(colored(f'{self.ts()}  [END]  {self.hostname} has been Patched successfully','green'))
                self.log(f'server has been Patched successfully','info')
                status = True
        elif status and recom and not self.yes:
            ans = input(f"do you want to restore region snapshots on {self.hostname}(y/n):")
            if ans.lower() == 'y':
                print(f'{self.ts()}  {self.hostname} [INFO] Recommission in progress')
                self.log(f'Recommission in progress','info')
                result,error  = self.local_exec(recom_cmd)
                DataLocality = self.data_locality()
                if DataLocality:
                    print(colored(f'{self.ts()}  [END]  {self.hostname} has been Patched successfully','green'))
                    self.log(f'server has been Patched successfully','info')
                    status = True

        if status:
            return True
        else:
            return False
