#!/usr/bin/env python
import os
import argparse
import time
import signal
import urllib
import boto3
import botocore
from datetime import datetime
import logging
import json
import sys


def initialize_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
     
    # create console handler and set level to info
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
 
    # create error file handler and set level to error
    handler = logging.FileHandler("error.log","w", encoding=None, delay="true")
    handler.setLevel(logging.ERROR)
    formatter = logging.Formatter("%(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
 
    # # create debug file handler and set level to debug
    # handler = logging.FileHandler("all.log","w")
    # handler.setLevel(logging.DEBUG)
    # formatter = logging.Formatter("%(levelname)s - %(message)s")
    # handler.setFormatter(formatter)
    # logger.addHandler(handler)


cf = boto3.client('cloudformation')
initialize_logger()
 

# usage: create-or-update.py [-h] --name NAME --templateurl TEMPLATEURL 
# --params PARAMS --use-previous-param 
# arguments:
#   -h, --help            show this help message and exit
#   --name NAME           the name of the stack to create.
#   --templateurl TEMPLATEURL
#                         the url where the stack template can be fetched.
#   --params PARAMS       the key value pairs for the parameters of the stack (as a query string).
#   --usepreviousparam    flag that makes the stack to use existing parameters
def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--name', type=str, required=True,
                       help='the name of the stack to create.')
    parser.add_argument('--templateurl', type=str, required=True,
                       help='the url where the stack template can be fetched.')
    parser.add_argument('--params', type=str, required=True,
                       help='the key value pairs for the parameters of the stack.')
    parser.add_argument('--usepreviousparam', action='store_true', required=False, help='flag that makes the stack to use existing parameters')
    args = parser.parse_args()

    logging.info("Processing CFN - {name}".format(name=args.name))
    if not is_valid(args.templateurl):
        exit()
    params = parse_parameters(args.params, args.usepreviousparam)
    logging.info("Parameters: {params}".format(params=params))

    forceCreate = True
    try:

        if forceCreate and stack_exists(args.name):
            waiter = delete_stack(args.name)
            waiter.wait(StackName=args.name)

        waiter = update_stack(args.name, args.templateurl, params) if stack_exists(args.name) else create_stack(args.name, args.templateurl, params)
        logging.info("...waiting for stack to be ready...")
        waiter.wait(StackName=args.name)
    except botocore.exceptions.ClientError as ex:
        error_message = ex.response['Error']['Message']
        if error_message == 'No updates are to be performed.':
            logging.info("No changes")
        else:
            raise


# parameters=[
#     {
#         'ParameterKey': 'string',
#         'ParameterValue': 'string',
#         'UsePreviousValue': False
#     },
# ],
def parse_parameters(params_as_querystring, use_previous=None):
    pairs = urllib.parse.parse_qs(params_as_querystring)
    parameters = []
    for key in pairs:
        kv = {
            "ParameterKey":key,
            "ParameterValue":pairs[key][0],
        }
        if use_previous != None:
            kv['UsePreviousValue'] = use_previous

        parameters.append(kv)

    return parameters

def is_valid(template_url):
    try:
        template_resp = cf.validate_template(TemplateURL=template_url)
        logging.info("template parameters : {param}".format(param=template_resp['Parameters']))
        return True
    except botocore.exceptions.ClientError as ex:
        logging.info("template validation error : {error_message}".format(error_message=ex.response['Error']['Message']))
        logging.error(ex)
        return False

def stack_exists(stack_name):
    stacks = cf.list_stacks()['StackSummaries']
    for stack in stacks:
        if stack['StackStatus'] == 'DELETE_COMPLETE':
            continue
        if stack_name == stack['StackName']:
            return True
    return False

def update_stack(name, template_url, params):
    logging.info('Updating {}'.format(name))
    stack_result = cf.update_stack(
        StackName=name,
        TemplateURL=template_url,
        Parameters=params)
    return cf.get_waiter('stack_update_complete')

def create_stack(name, template_url, params):
    logging.info('Creating {}'.format(name))
    stack_result = cf.create_stack(
        StackName=name,
        TemplateURL=template_url,
        Parameters=params,
        Capabilities=['CAPABILITY_IAM','CAPABILITY_NAMED_IAM','CAPABILITY_AUTO_EXPAND'],
        DisableRollback=False)
    return cf.get_waiter('stack_create_complete')

def delete_stack(name):
    logging.info('Deleting {}'.format(name))
    stack_result = cf.delete_stack(
        StackName=name)
    return cf.get_waiter('stack_delete_complete')

if __name__ == '__main__':
    main()