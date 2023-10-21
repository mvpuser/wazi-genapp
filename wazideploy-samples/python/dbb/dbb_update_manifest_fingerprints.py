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

from pathlib import Path
import yaml
import json
import re

from wazideploy.service.utilities import Utilities

class GitUtilities(object):
     
    @staticmethod
    def get_current_git_hash(git_dir: str):
        #cmd = f"git -C {git_dir} rev-list -1 --abbrev=8 HEAD {file_path}"
        cmd = f"git -C {git_dir} rev-parse --short=8 HEAD"
        rc, out, err = Utilities.run_command(cmd)
        if rc != 0:
            msgstr = f"*! Error executing Git command: {cmd} error: {err}"
            print(msgstr)
        return out.strip()
    
    @staticmethod
    def get_current_git_url(git_dir: str):
        cmd = f"git -C {git_dir} config --get remote.origin.url"
        rc, out, err = Utilities.run_command(cmd)
        if rc != 0:
            msgstr = f"*! Error executing Git command: {cmd} error: {err}"
            print(msgstr)
        return out.strip()
    
    @staticmethod
    def get_current_git_branch(git_dir: str):
        cmd = f"git -C {git_dir} rev-parse --abbrev-ref HEAD"
        rc, out, err = Utilities.run_command(cmd)
        if rc != 0:
            msgstr = f"*! Error executing Git command: {cmd} error: {err}"
            print(msgstr)
        return out.strip()
    
    @staticmethod
    def is_git_detached_head(git_dir: str):
        cmd = f"git -C {git_dir} status"
        rc, out, err = Utilities.run_command(cmd)
        if rc != 0:
            msgstr = f"*! Error executing Git command: {cmd} error: {err}"
            print(msgstr)
    
        return "HEAD detached at" in out.strip()

    @staticmethod
    def get_current_git_detached_branch(git_dir: str):
        cmd = f"git -C {git_dir} show -s --pretty=%D HEAD"
        rc, out, err = Utilities.run_command(cmd)
        if rc != 0:
            msgstr = f"*! Error executing Git command: {cmd} error: {err}"
            print(msgstr)
            
        git_branch_string = out.strip()
        git_branch_arr = git_branch_string.split(',')
        solution = ""
        for branch in git_branch_arr:
            if "origin/" in branch:
                solution = re.sub('.*?/', '', branch).strip()
        if solution == "":
            print(f"*! Error parsing branch name: {branch}")
        else:
            return solution

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

def dbb_update_manifest(**kwargs):
    dbb_build_result_file = kwargs['dbbBuildResult']
    source_folder = kwargs['sourceFolder']
    manifest_file = kwargs['manifest']

    print((f"** Update the manifest {manifest_file}"))
    buildResult = DBBUtilities.read_build_result(dbb_build_result_file)
    records = list(filter(lambda record: DBBUtilities().filter_deployable_records(record),buildResult['records']))
    
    with open(manifest_file, 'r') as stream:
        manifest_dic = dict (yaml.safe_load(stream))

    scm = {}
    scm['type'] = 'git'
    scm['uri'] = re.sub(r'\/.*@', '//', GitUtilities.get_current_git_url (source_folder))
    if GitUtilities.is_git_detached_head(source_folder):
        scm['branch'] = GitUtilities.get_current_git_detached_branch(source_folder)
    else:
        scm['branch'] = GitUtilities.get_current_git_branch (source_folder)
    scm['short_commit'] = GitUtilities.get_current_git_hash (source_folder)
    manifest_dic['metadata']['annotations']['scm'] = scm
        
    for record in buildResult['records']:
        if record.get('url') is not None:
            manifest_dic['metadata']['annotations']['dbb'] = {}
            manifest_dic['metadata']['annotations']['dbb']['build_result_uri'] = record.get('url')
            break

    for record in records:
        dataset = record['dataset']
        deploy_type = record['deployType']
        parts = re.split('\\(|\\)',dataset)
        member_name = parts[1]
        pds_name = parts[0]
        
        for artifact in manifest_dic['artifacts']:
            if artifact['name'] == member_name:
                path_prop = list(filter(lambda prop: ('path' == prop['key']), artifact['properties']))
                if len(path_prop) > 0:
                    path = path_prop[0]['value']
                    parts = re.split('/',path)
                
                if parts[0] == pds_name:
                    copyMode = DBBUtilities.get_copy_mode(artifact['type'], **kwargs)
                        
                    if copyMode == 'LOAD':
                        fingerprint = Utilities.get_loadmodule_idrb(f"{pds_name}({artifact['name']})")
                    else:
                        fingerprint = artifact['hash']
                    
                    msgstr = f"** Register fingerprint for '{pds_name}({artifact['name']})':  {fingerprint}"
                    print(msgstr)
                    
                    fingerprint_prop = list(filter(lambda prop: ('fingerprint' == prop['key']), artifact['properties']))
                    if len(fingerprint_prop) > 0:
                        fingerprint_prop[0]['value'] = f"{fingerprint}"
                    else:
                        artifact['properties'].append(
                            {"key": "fingerprint",
                             "value": f"{fingerprint}"})

    Utilities.dump_to_yaml_file(manifest_dic, manifest_file)

def main(): 
    
        parser = argparse.ArgumentParser(description="DBB Update Manifest")
        parser.add_argument('-br', '--dbbBuildResult', required=True, help='The DBB build result file')
        parser.add_argument('-sf', '--sourceFolder', required=True, help='The path to the source folder')
        parser.add_argument('-m', '--manifest', help='The path to the manifest to update')
        
        if len(sys.argv[1:]) == 0:
            parser.print_help()
            return

        args = parser.parse_args()
        kwargs=vars(args)

        dbb_update_manifest (**kwargs)

if __name__ == '__main__':
    main()