#*******************************************************************************
# Licensed Materials - Property of IBM
# (c) Copyright IBM Corp. 2023. All Rights Reserved.
#
# Note to U.S. Government Users Restricted Rights:
# Use, duplication or disclosure restricted by GSA ADP Schedule
# Contract with IBM Corp.
#*******************************************************************************

import argparse
import sys
import os
import platform
import re
import json
import subprocess
from pathlib import Path

class DBBUtilities(object):

    @staticmethod
    def filter_deployable_records(record) -> bool:
        try:
            if (record['type'] == 'EXECUTE' or record['type'] == 'COPY_TO_PDS') and len(record['outputs']) > 0:
                for output in record['outputs']:
                    try:
                        if output['deployType']:
                            record['deployType']=output['deployType']
                            record['dataset']=output['dataset']
                            return True
                    except:
                        pass
        except:
            pass
        return False

    @staticmethod
    def filter_deleted_records(record) -> bool:
        try:
            if record.get('deletedBuildOutputs'):
                return True
        except:
            pass
        return False

    @staticmethod
    def read_build_result(read_build_result_file) -> dict:
        with open(read_build_result_file) as read_file:
            return dict(json.load(read_file))

    @staticmethod
    def get_copy_mode(deployType:str = "LOAD", **kwargs) -> str:
        if kwargs.get('copyModeProperties') is not None:
            props = {}
            props_yaml_file = kwargs['copyModeProperties']
            try:
                with open(props_yaml_file, 'r') as stream:
                    props = dict (yaml.safe_load(stream))
                    if props.get(deployType) is not None:
                        return props.get(deployType)
            except IOError as error: 
                print(error, file=sys.stderr)
                raise RuntimeError(f"!!! Couldn't open target environment file from: {props_yaml_file} !!!")
        if re.search('LOAD', deployType, re.IGNORECASE):
            return "LOAD"
        elif re.search('DBRM', deployType, re.IGNORECASE):
            return "BINARY"
        elif re.search('TEXT', deployType, re.IGNORECASE):
            return "TEXT"
        elif re.search('COPY', deployType, re.IGNORECASE):
            return "TEXT"
        elif re.search('OBJ', deployType, re.IGNORECASE):
            return "BINARY"
        elif re.search('DDL', deployType, re.IGNORECASE):
            return "TEXT"
        elif re.search('JCL', deployType, re.IGNORECASE):
            return "TEXT"
        else:
            return "TEXT"

def run_command (command: str, verbose: bool = True):
    process = subprocess.run(command.split(), capture_output=True, text=True)

    if process.returncode != 0 and verbose:
        print("stdout:", process.stdout, file=sys.stdout)
        print("stderr:", process.stderr, file=sys.stderr)

    return process.returncode, process.stdout, process.stderr

def copy_dbb_build_result_to_local_folder(**kwargs):
    dbb_build_result_file = kwargs['dbbBuildResult']
    working_folder = kwargs['workingFolder']
   
    # Units
    buildResult = DBBUtilities.read_build_result(dbb_build_result_file)
    
    records = list(filter(lambda record: DBBUtilities().filter_deployable_records(record),buildResult['records']))
    for record in records:
        dataset = record['dataset']
        deploy_type = record['deployType']
        parts = re.split('\\(|\\)',dataset)
        member_name = parts[1]
        pds_name = parts[0]
    
        # Build the local_folder from DBB Build Outputs
        msgstr = f"** Copy //'{dataset}' to {working_folder}/{pds_name}/{member_name}.{deploy_type}"
        print(msgstr)
        
        os.makedirs(f"{working_folder}/{pds_name}", exist_ok=True)
        copyMode = DBBUtilities.get_copy_mode(deploy_type, **kwargs)
        if copyMode == 'LOAD':
            cmd = f"cp -XI //'{dataset}' {working_folder}/{pds_name}/{member_name}.{deploy_type}"

        elif copyMode == 'BINARY':
            cmd = f"cp -F bin //'{dataset}' {working_folder}/{pds_name}/{member_name}.{deploy_type}"
        else:
            cmd = f"cp //'{dataset}' {working_folder}/{pds_name}/{member_name}.{deploy_type}"

        if platform.system() == 'OS/390':
            rc, out, err = run_command(cmd)
            if rc != 0:
                msgstr = f"*! Error executing command: {cmd} out: {out} error: {err}"
                print(msgstr)
                sys.exit(-1)
            cmd = f"chtag -b {working_folder}/{pds_name}/{member_name}.{deploy_type}"
            rc, out, err = run_command(cmd)
            if rc != 0:
                msgstr = f"*! Error executing command: {cmd} out: {out} error: {err}"
                print(msgstr)
                sys.exit(-1)

def main(): 

        parser = argparse.ArgumentParser(description="DBB Prepare Package")
        parser.add_argument('-br', '--dbbBuildResult', required=True, help='The DBB build result file')
        parser.add_argument('-wf', '--workingFolder', required=True, help='The path to the working folder')
        parser.add_argument('-cp', '--copyModeProperties', help='The path to the file that contains copy mode properties')
        
        if len(sys.argv[1:]) == 0:
            parser.print_help()
            return

        args = parser.parse_args()
        
        kwargs=vars(args)

        copy_dbb_build_result_to_local_folder (**kwargs)

if __name__ == '__main__':
    main()