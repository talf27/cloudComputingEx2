from flask import Flask, request
import requests
import time
import threading
import boto3
import paramiko
import os
import base64
import pickle

app = Flask(__name__)


class API:
    # Queue of 3-tuples (work_id, data, iterations) for enqueue requests
    enqueue_tasks_queue = []
    # Queue of 'top' parameters of pullCompleted requests
    pull_tasks_queue = []

    # List to store completed work items, each one is a string in the format: 'work_id:xxx,value:xxx'
    completed_work = []

    ec2_client = boto3.client('ec2', 'eu-west-1')
    ec2_resource = boto3.resource('ec2', 'eu-west-1')

    # the **only** difference from the code in the other instance
    response = ec2_client.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': ['mainMachine1']}])
    other_main_machine = response['Reservations'][0]['Instances'][0]
    other_main_machine_ip = other_main_machine['PublicIpAddress']

    response = ec2_client.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': ['firstWorker']}])
    first_worker = response['Reservations'][0]['Instances'][0]
    first_worker_ip = first_worker['PublicIpAddress']
    first_worker_keypair = first_worker['KeyName']

    # Queue of the free workers, can be maximum 5.
    # each element is a 3-tuple with the instance's IP, key pair name, and the time it was freed.
    free_workers_queue = [(first_worker_ip, first_worker_keypair, time.time())]
    workers_num = 1

    # Endpoint for enqueuing user-submitted data
    @app.route('/enqueue', methods=['PUT'])
    def enqueue_data():
        iterations = request.args.get('iterations')
        data = request.data

        work_id = time.time()
        API.enqueue_tasks_queue.append((work_id, data, iterations))

        if len(API.free_workers_queue) == 0 and API.workers_num < 5:
            # Create a new worker if there are no free workers right now and
            # there are no more than 5 existing workers.
            # Create in a new thread because it takes time
            thread = threading.Thread(target=scale_up)
            thread.start()
        elif len(API.free_workers_queue) > 0:
            # there are free workers - make the enqueue task!
            enqueue_task()

        return f"work_id: {work_id}"

    # Endpoint for pulling completed work items
    @app.route('/pullCompleted', methods=['POST'])
    def pull_completed_work():
        top = request.args.get('top')

        API.pull_tasks_queue.append(top)

        if len(API.free_workers_queue) == 0:
            if API.workers_num < 5:
                # Create a new worker if there are no free workers right now and
                # there are no more than 5 existing workers.
                # Create in a new thread because it takes time
                thread = threading.Thread(target=scale_up)
                thread.start()
            # There are no free workers right now so the program can't return output at the moment...
            return "all workers are busy, please try again in a few seconds..."

        # there are free workers - make the pullCompleted task!
        completed_work_items = pull_task()
        return completed_work_items

    # Endpoint for receiving updates about a completed work item from the other main instance
    @app.route('/receiveUpdateEnqueue', methods=['PUT'])
    def receive_update_enqueue():
        new_work = request.args.get('newWork')
        API.completed_work.append(new_work)


def enqueue_task():
    # Dequeue the first from the enqueue_tasks_queue
    work_id, data, iterations = API.enqueue_tasks_queue.pop(0)

    # Dequeue the first free worker to run the enqueue task
    worker_ip, worker_keypair, _ = API.free_workers_queue.pop(0)

    # connect remotely to the worker
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(hostname=worker_ip, username='ubuntu', key_filename=worker_keypair + '.pem')

    # ***unsuccessful code:***
    # Execute the Python program worker.py, who is responsible for the enqueue task and pullCompleted task,
    # and is meant to be transferred by scp in the original bash script setup.sh, remotely on the new instance.
    # The python execution doesn't return nothing...
    # remote_path = '/home/ubuntu/worker.py'
    # method_name = 'enqueue_task'
    # method_params = [data.decode(), iterations]
    # command = f'python {remote_path} {method_name} {" ".join(method_params)}'

    # ***unsuccessful code:***
    # Communicate with the worker by HTTP Endpoint
    # (with the required changes on the method in the worker.py program
    # to ba an HTTP endpoint and not a regular method of course,
    # and also needed to update the security group of the workers to be open inbound in port 5000).
    # Unfortunately, it gets an error from requests.exceptions.ConnectionError
    # about Max retries exceeded [Errno 111]
    # url = f'http://{worker_ip}:5000/enqueueWorker'
    # data_for_request = data
    # params_for_requests = {'iterations': iterations}
    # response = requests.put(url, data=data_for_request, params=params_for_requests)

    # Instead of running in python code or by an HTTP endpoint, run in a bash script
    script_path = 'enqueue.sh'
    encoded_data = base64.b64encode(data).decode().strip()
    command = f'bash {script_path} "{encoded_data}" {iterations}'
    std_in, std_out, std_err = ssh_client.exec_command(command)

    # Retrieve the output of the method
    value = std_out.read().decode('utf-8').strip()
    ssh_client.close()

    output = f'work_id:{work_id},value:{value}'
    API.completed_work.append(output)

    # The worker finished the enqueue process and now is free again.
    API.free_workers_queue.append((worker_ip, worker_keypair, time.time()))
    # The main machine updates the another main machine about the new completed work.
    send_update_enqueue(output)
    # If there are pull requests waiting for some worker, so now this worker got free,
    # then pull_task() can be called. Same with enqueue_task() (pull requests are preferable).
    if len(API.pull_tasks_queue) > 0:
        pull_task()
    elif len(API.enqueue_tasks_queue) > 0:
        enqueue_task()


def pull_task():
    # Dequeue the first from the pull_tasks_queue
    top = API.pull_tasks_queue.pop(0)

    # Dequeue the first free worker to run the pull task
    worker_ip, worker_keypair, _ = API.free_workers_queue.pop(0)

    # Execute the Python program remotely on the new instance
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(hostname=worker_ip, username='ubuntu', key_filename=worker_keypair + '.pem')

    # ***unsuccessful code:***
    # Execute the Python program worker.py, who is responsible for the enqueue task and pullCompleted task,
    # and is meant to be transferred by scp in the original script bash setup.sh, remotely on the new instance.
    # The python execution doesn't return nothing...
    # remote_path = '/home/ubuntu/worker.py'
    # method_name = 'pull_task'
    # Send the completed_work list as serialized string
    # serialized_list = pickle.dumps(API.completed_work)
    # encoded_list = base64.b64encode(serialized_list).decode()
    # method_params = [encoded_list, top]
    # command = f'python {remote_path} {method_name} {" ".join(method_params)}'

    # Instead of running in python code, run in a bash script
    script_path = 'pull.sh'
    completed_work_str = ' '.join(API.completed_work)
    command = f'bash {script_path} "{completed_work_str}" {top}'
    std_in, std_out, std_err = ssh_client.exec_command(command)

    # Retrieve the output of the method
    output = std_out.read().decode('utf-8')
    ssh_client.close()

    # The worker finished the enqueue process and now is free again.
    API.free_workers_queue.append((worker_ip, worker_keypair, time.time()))

    # modify the list of completed_work without the 'top' last works
    if int(top) > len(API.completed_work):
        API.completed_work = []
    else:
        API.completed_work = API.completed_work[:-int(top)]

    return output


# method for updating the other main instance when a new work was made and its value was calculated
def send_update_enqueue(new_work):
    url = f'http://{API.other_main_machine_ip}:5000/receiveUpdateEnqueue'
    params_for_requests = {'newWork': new_work}
    requests.put(url, params=params_for_requests)


def scale_up():
    key_pair_name = API.first_worker_keypair
    security_group_id = get_security_group()

    # Launch an EC2 instance as a new worker
    launching_response = API.ec2_client.run_instances(
        ImageId='ami-01dd271720c1ba44f',
        InstanceType='t2.micro',
        UserData='''#!/bin/bash
                    nohup flask run --host 0.0.0.0 &>/dev/null &''',
        SecurityGroupIds=[security_group_id],
        MinCount=1,
        MaxCount=1,
        KeyName=key_pair_name
    )

    # using waiter instead of time.sleep() doesn't give the required purpose
    # and the program tries to connect the new instance via SSH too early for some reason...
    time.sleep(25)

    new_worker_id = launching_response['Instances'][0]['InstanceId']
    # Inserts the new created worker to the free workers list as the last one
    API.free_workers_queue.append((new_worker_id, key_pair_name, time.time()))
    API.workers_num += 1
    new_worker_response = API.ec2_client.describe_instances(InstanceIds=[new_worker_id])
    new_worker_ip = new_worker_response['Reservations'][0]['Instances'][0]['PublicIpAddress']

    # Establish SSH connection
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(hostname=new_worker_ip, username='ubuntu', key_filename=key_pair_name + '.pem')

    # Transfer the Bash scripts to the new instance
    sftp_client = ssh_client.open_sftp()
    sftp_client.put('enqueue.sh', '/home/ubuntu/enqueue.sh')
    sftp_client.put('pull.sh', '/home/ubuntu/pull.sh')
    # sftp_client.put('worker.py', '/home/ubuntu/worker.py')
    sftp_client.close()

    # Run periodically checks for scaling down if this newly created worker
    # is the first one (ever or after all previous workers were terminated)
    if len(API.free_workers_queue) == 1:
        thread = threading.Thread(target=check_for_scale_down)
        thread.start()


def get_security_group():
    vpc_response = API.ec2_client.describe_vpcs()
    vpc_id = vpc_response['Vpcs'][0]['VpcId']

    sec_group_response = API.ec2_client.describe_security_groups(
        Filters=[
            {'Name': 'group-name', 'Values': ['sec-grp-for-workers']},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    )
    security_group_id = sec_group_response['SecurityGroups'][0]['GroupId']

    return security_group_id


def check_for_scale_down():
    # Keeps the number of free workers at least 1
    # for avoiding long response time for HTTP requests if there are no workers at all
    while len(API.free_workers_queue) > 1:
        # if the first free worker is freed for at least 5 minutes, terminate it.
        if time.time() - API.free_workers_queue[0][2] >= 300:
            API.ec2_client.terminate_instances(InstanceIds=[API.free_workers_queue.pop(0)[0]])
            API.workers_num -= 1
        # Otherwise, check again in 2 minutes.
        else:
            time.sleep(120)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
