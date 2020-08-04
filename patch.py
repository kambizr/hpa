import subprocess
import yaml
import time
import sys
import os
from termcolor import colored
from datetime import datetime
import re
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
    def __init__(self,hostname):
        self.hostname = hostname

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
                    sys.exit(2)
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
                        print(f'{self.ts()}  [INFO] {cmd} executed successfully')
        elif key:
            for cmd in patch_conf[key]:
                result,error =  self.exec(cmd)
                if not error :
                    print(f'{self.ts()}  [INFO] {cmd} executed successfully')




    def validation(self,conf):
        for check in conf:
            result,error = self.exec(conf[check]['cmd'])
            if not error:
                if conf[check]['msg'] not in str(result):
                    print(colored(f'{self.ts()}  [VRF]  {check} Verified','green'))
                elif conf[check]['msg'] in str(result):
                    print(colored(f'{self.ts()}  [VRF]  {check} Needs Update try to update it....','red'))
                    while True:
                        self.patching(check)
                        result,error = self.exec(conf[check]['cmd'])
                        if conf[check]['msg'] not in str(result):
                            print(colored(f'{self.ts()}  [VRF]  {check} Verified','green'))
                            break
                        else:
                            print(colored(f'{self.ts()}  [VRF]  {check} Needs Update try to update it....','red'))
                            break
                else:
                    print(f'{self.ts()}  [INFO]  {check} is not installed in this server')
            else:
                print(colored(f'{self.ts()}  [ERR]  ERROR: {error}','red'))




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
        compact =  str(match.group(3)+match.group(4)+str(new_ts).strip()+"'")
        with open(f'./dataLocality/after_activity_{self.hostname}') as file:
            lines = file.readlines()
        print(f'{self.ts()}  [INFO]  Moving regions in progress...')
        for line in lines:
            move = query1 =f'echo "{line.strip()}" | hbase shell '
            result,error =  self.exec(move)


        comapc_rs = f'echo "compact_rs {compact},true" | habse shell'
        self.exec(comapc_rs)

        print(int(match_dl.group(2)))
        while True :
            result,error = self.exec(detailed_node)
            pattern_DL = re.compile(r'(dataLocality=)(\d?)')
            match_dl = re.search(pattern_DL,str(result))
            if float(match_dl.group(2)) < 0.90:
                break
            time.sleep(1)
        else:
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

        #################Pre patching####################
        #copy Kevin's script to the node to take snapshot
        result,error = self.local_exec(sn_cp)
        if error:
            print(colored(f'{self.ts()}  [ERR] {error}','red'))
        else:
            print(f'{self.ts()}  [INFO] ToolBox-assembly-0.1.0-SNAPSHOT.jar Copied sucessfully')
        result,error = self.local_exec(sn_exe_cp)
        if error:
            print(colored(f'{self.ts()}  [ERR] {error}','red'))
        else:
            print(f'{self.ts()}  [INFO] run.sh Copied sucessfully')

        #execute Kevin's script to make a snapshot
        result,error =  self.exec(config['recom_exe']['cmd2']['cmd'])
        if str(config['recom_exe']['cmd2']['msg']).lower() in str(result):
            result,error = self.exec("sh ~/run.sh")
            if result:
                print(f'{self.ts()}  [INFO] Snapshot created sucessfully')
        else:
            print(f'{self.ts()}  [INFO] Host is not in Noraml stage')

        #Decommission the node

        decom = False
        i = 1
        while i <= 3:
            result,error  = self.local_exec(decom_cmd)
            if '[INFO] SUCCESS! HCM decommissioning process for' in result or '[INFO] SUCCESS! HCM decommissioning process for' in error:
                print(f'{self.ts()}  [INFO] Decommission command ran successfully')
                decom = True
                break
            else:
                print(colored(f'{self.ts()}  [WRN]  Retry NO.{i} of 3 to Recommisioning is failed','yellow'))
                i += 1
        if not decom:
            print(colored(f'{self.ts()}  [ERR]   Script Exit Because Node could not be decommissioned','red'))
            sys.exit(2)

        # print(f'{self.ts()}  [INFO] Run the puppet')
        # result,error = self.exec(puppet)
        # if error:
        #     print(colored(f'{self.ts()}  [ERR] {error}','red'))
        # else:
        #     print(f'{self.ts()}  [INFO] Puppetrun fnished sucessfully ')

        # #run general prep commands:
        prep_srvs = sn_exe = config['all_prep']['service'].keys()
        for srv in prep_srvs:
            cmd = config['all_prep']['service'][srv]['cmd']
            vrf = config['all_prep']['service'][srv]['vrf']
            msg =  config['all_prep']['service'][srv]['msg']
            print(f'{self.ts()}  [INFO] RUN: {cmd} ')
            result,error = self.exec(cmd)
            if error:
                print(colored(f'{self.ts()}  [ERR]  Error on {srv}:  {error} ','red'))
            else:
                result,error = self.exec(vrf)
                time.sleep(2)
                if msg in str(result):
                    print(colored(f'{self.ts()}  [VRF]  {srv} verified for pre Patching','green'))
                else:
                    print(colored(f'{self.ts()}  [ERR]  {srv} not verified for Pre-Patching Message:\n {result}','red'))

        #execute special prep command for specific nodes
        types =  config['node_prep_type']
        for type in types.keys():
            if type in self.hostname:
                type_cmds = config['node_prep_type'][type].keys()
                print(colored(f'{self.ts()}  [MSG]  it is {type} node ','cyan'))
                for cmds in type_cmds:
                    cmd = config['node_prep_type'][type][cmds]['cmd']
                    vrf = config['node_prep_type'][type][cmds]['vrf']
                    msg = config['node_prep_type'][type][cmds]['msg']
                    print(f'{self.ts()}  [INFO] run {cmd} ')
                    result,error = self.exec(cmd)
                    if error:
                        print(colored(f'{self.ts()}  [ERR]  ERROR on: {cmds}: {error} ','red'))
                    else:
                        result,error = self.exec(vrf)
                        if error:
                            print(colored(f'{self.ts()}  [ERR]  Verification ERROR on: {cmds}: {error} ','red'))
                        else:
                            if msg in result:
                                print(colored(f'{self.ts()}  [VRF]  {cmds} verified for pre Patching','green'))
                            else:
                                print(colored(f'{self.ts()}  [ERR]  {cmds} not verified for Pre-Patching Message:\n {result}','red'))

        #Decomission verification
        print(f'{self.ts()}  [INFO] Decommission in progress')
        t =  0
        while True:
            if t == 7200:
                print(colored(f'{self.ts()}  [ERR]  decommission Timeout  ','red'))
                sys.exit(2)
            result,error = self.exec(config['decom_verify']['cmd'])
            if config['decom_verify']['msg'] in result.lower():
                print(colored(f'{self.ts()}  [VFY]  Node verified: Decommissioned ','green'))
                break
            else:
                t =+1
                time.sleep(1)

        # ######################Patching#######################
        ans = input("do you want patch:")
        if ans != 'y':
            sys.exit()
        self.patching()

        ###################Rebooting####################

        print(colored(f'{self.ts()}  [WRN]  reboot {self.hostname}','yellow'))
        ans = input("do you want reboot:")
        if ans != 'y':
            sys.exit()
        result = self.reboot()
        if result :
            while True:
                time.sleep(5)
                result,error = self.exec('uname -r')
                if not error:
                    break

            print(f'{self.ts()}  [INFO] {self.hostname} rebooted successfully')


        ####################### Post patching#########################
        #patching validation
        self.validation(config['validation'])


        ############recommission the node
        ans = input("do you want recommisiion:")
        if ans != 'y':
            sys.exit()
        i = 1
        recom = False
        while i <= 3:
            result,error  = self.local_exec(recom_cmd)
            if 'SUCCESS! HCM recommissioning process for' in result or 'SUCCESS! HCM recommissioning process for' in error:
                print(f'{self.ts()}  [INFO]  Recommission command finished successfully')
                print(f'{self.ts()}  [INFO] sleep 2 mins then Run the puppet')
                time.sleep(120)
                print(f'{self.ts()}  [INFO] Puppet is running...')
                result,error = self.exec(puppet)
                if error:
                    print(colored(f'{self.ts()}  [ERR] {error}','red'))
                else:
                    print(f'{self.ts()}  [INFO] Puppetrun fnished sucessfully ')
                recom = True
                break
            else:
                print(colored(f'{self.ts()}  [WRN]  Retry NO.{i} of 3 to Recommisioning is failed','yellow'))
                i += 1
        if not recom:
            print(colored(f'{self.ts()}  [ERR]   Script Exit Because Node could not be decommissioned','red'))
            sys.exit(2)

        # #Start Services
        post_srvs = sn_exe = config['all_post']['service'].keys()
        for srv in post_srvs:
            cmd = config['all_post']['service'][srv]['cmd']
            vrf = config['all_post']['service'][srv]['vrf']
            msg =  config['all_post']['service'][srv]['msg']
            print(f'{self.ts()}  [INFO] RUN: {cmd} ')
            result,error = self.exec(cmd)
            if error:
                print(colored(f'{self.ts()}  [ERR]  Error on {srv}:  {error} ','red'))
            else:
                result,error = self.exec(vrf)
                time.sleep(2)
                if msg in str(result):
                    print(colored(f'{self.ts()}  [VRF]  {srv} verified for Post Patching','green'))
                else:
                    print(colored(f'{self.ts()}  [ERR]  {srv} not verified for Post Patching Message:\n {result}','red'))

        types =  config['node_post_type']
        for type in types.keys():
            if type in self.hostname:
                type_cmds = config['node_post_type'][type].keys()
                print(colored(f'{self.ts()}  [MSG]  it is {type} node ','cyan'))
                for cmds in type_cmds:
                    cmd = config['node_post_type'][type][cmds]['cmd']
                    vrf = config['node_post_type'][type][cmds]['vrf']
                    msg = config['node_post_type'][type][cmds]['msg']
                    print(f'{self.ts()}  [INFO] run {cmd} ')
                    result,error = self.exec(cmd)
                    if error:
                        print(colored(f'{self.ts()}  [ERR]  ERROR on: {cmds}: {error} ','red'))
                    else:
                        result,error = self.exec(vrf)
                        if error:
                            print(colored(f'{self.ts()}  [ERR]  Verification ERROR on: {cmds}: {error} ','red'))
                        else:
                            if msg in result:
                                print(colored(f'{self.ts()}  [VRF]  {cmds} verified for post patching','green'))
                            else:
                                print(colored(f'{self.ts()}  [ERR]  {cmds} not verified for post patching Message:\n {result}','red'))


        # Recommission verification
        vrf1 = False
        vrf2 = False
        i = 1

        while i <= 3:
            print(f'{self.ts()}  [INFO] Retry: {i} Recommissioning Verifivation')
            if not vrf1:
                result,error =  self.exec(config['recom_exe']['cmd1']['cmd'])
                if str(config['recom_exe']['cmd1']['msg']).lower() in str(result):
                    print(colored(f'{self.ts()}  [VRF]  recommissioning verified 1 of 2 ','green'))
                    vrf1 = True
                else:
                    print(colored(f'{self.ts()}  [ERR]  Retry NO.{i} recommissioning verified 1 of 2 failed ','red'))
            if not vrf2:
                result,error =  self.exec(config['recom_exe']['cmd2']['cmd'])
                if str(config['recom_exe']['cmd2']['msg']).lower() in str(result):
                    vrf2 =  True
                    print(colored(f'{self.ts()}  [VRF]  recommissioning verified 2 of 2 ','green'))
                else:
                    print(colored(f'{self.ts()}  [ERR]  Retry NO.{i} recommissioning verified 2 of 2 failed ','red'))
            if vrf1 and vrf2:
                print(colored(f'{self.ts()}  [VRF]  {self.hostname} verified: Recommissioned ','green'))
                break
            i += 1
        if not vrf1 or not vrf2:
             print(colored(f'{self.ts()}  [ERR]  Node recommissio Failed ','red'))
             sys.exit(2)
        ans = input("do you want to move regions:")
        if ans != 'y':
            sys.exit()
        DataLocality = self.data_locality()
        if DataLocality:
            print(colored(f'{self.ts()}  [END]  {self.hostname} has been Patched successfully','green'))



def main():
    try:
        yes = False
        start = time.time()
        if len(sys.argv) == 3:
            if '-y' in sys.argv[3]:
                yes = True
            else:
                print(colored("Wrong arguments just one host name ",'red'))
                sys.exit(2)

        if  len(sys.argv) <= 1:
            print(colored("Please add your FQDN as an argument e.g. # python3 patch.py jm-data3154.lv7.box.net [-y]",'red'))
            sys.exit(2)
        elif len(sys.argv) == 2  and 'box.net' not in sys.argv[1]:
            print(colored("Please ENTER FQDN",'red'))
            sys.exit(2)
        elif len(sys.argv) > 3:
            print(colored("Please add your FQDN as an argument e.g. # python3 patch.py jm-data3154.lv7.box.net [-y]",'red'))
            sys.exit(2)
        elif len(sys.argv) >= 2 and 'box.net' in sys.argv[1]:
            print(yes)
            print(str(sys.argv[1]))
            # obj = Patch(str(sys.argv[1],yes))
            # obj.patch()
        end = time.time()
        total = end - start
        if total > 60:
            total = int(total/60)
            print(colored(f'###Execution time is {total} Minutes for {sys.argv[1]}###','white', 'on_blue',['bold','blink']))
        else:
            print(colored(f'###Execution time is {int(total)} seconds for {sys.argv[1]}###','white', 'on_blue',['bold','blink']))
    except KeyboardInterrupt:
        print("Interrupted")


if __name__ == "__main__":
    main()
