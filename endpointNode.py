from flask import Flask, request, make_response, abort
import threading
import requests
import time
import boto3
import paramiko

app = Flask(__name__)


class EndpointNode:
    # Queue of dictionaries each contains: work_id (the enqueued time), data, iterations number.
    work_queue = []

    # List to store completed work items as tuples of (work_id, hashed_value)
    completed_work = []

    num_of_workers = 0
    max_num_of_workers = 3

    ec2_client = boto3.client('ec2', 'eu-west-1')

    my_ip = None
    other_node_ip = None
    # using the same security group and keypair for launching new workers and save redundancy.
    sec_grp_id_for_workers = None
    keypair_for_workers = None

    # List of IP addresses of all the workers, also ones created by the other node,
    # to manage IP restriction of endpoints that are meant to be accessed only by the workers.
    allowed_workers_ip = []

    # Endpoint for enqueuing user-submitted data
    @app.route('/enqueue', methods=['PUT'])
    def enqueue_data():
        work_id = time.time()
        data = request.data
        iterations = request.args.get('iterations')

        EndpointNode.work_queue.append({'work_id': str(work_id), 'data': str(data), 'iterations': iterations})

        return f"work id: {work_id}"

    # Endpoint for pulling completed work items
    @app.route('/pullCompleted', methods=['POST'])
    def pull_completed_work():
        top = int(request.args.get('top'))

        if len(EndpointNode.completed_work) > 0:
            if top < len(EndpointNode.completed_work):
                items_to_return = [EndpointNode.completed_work.pop() for _ in range(top)][::-1]
            else:
                items_to_return, EndpointNode.completed_work = EndpointNode.completed_work, []
        else:
            try:
                url = f'http://{EndpointNode.other_node_ip}:5000/pullCompletedInternal'
                params = {'top': request.args.get('top')}
                response = requests.post(url, params=params)
                return response.content
            except:
                return "There are no completed work items right now..."

        return '\n'.join([f"work_id: {work_item[0]}, value: {work_item[1]}" for work_item in items_to_return])

    # Endpoint accessed by workers to get a new work item
    @app.route('/getWorkItem', methods=['GET'])
    def get_work_item():
        source_ip = request.remote_addr
        if is_access_allowed_workers(source_ip):
            if len(EndpointNode.work_queue) > 0:
                response = make_response(EndpointNode.work_queue.pop(0))
                response.status_code = 200
            else:
                response = make_response('')
                response.status_code = 204

            return response

    # Endpoint accessed by workers for updating in a completed work item
    @app.route('/updateCompletedWork', methods=['PUT'])
    def update_completed_work():
        source_ip = request.remote_addr
        if is_access_allowed_workers(source_ip):
            work_id = request.args.get('work_id')
            value = request.args.get('value')
            EndpointNode.completed_work.append((work_id, value))

            return '', 204

    # Endpoint accessed by the other node which has no completed work items
    # to check if the current node has.
    # Not like the other pullCompleted endpoint, this endpoint won't ask the other node
    # for completed work items if the current node has no items either.
    @app.route('/pullCompletedInternal', methods=['POST'])
    def pull_completed_work_internal():
        source_ip = request.remote_addr
        if is_access_allowed_other_node(source_ip):
            top = int(request.args.get('top'))

            if len(EndpointNode.completed_work) > 0:
                if top < len(EndpointNode.completed_work):
                    items_to_return = [EndpointNode.completed_work.pop() for _ in range(top)][::-1]
                else:
                    items_to_return, EndpointNode.completed_work = EndpointNode.completed_work, []
            else:
                return "There are no completed work items right now..."

            return '\n'.join([f"work_id: {work_item[0]}, value: {work_item[1]}" for work_item in items_to_return])

    # Endpoint accessed by the other node to check load balancing with the workers number for each node
    @app.route('/hasExtraWorkers', methods=['GET'])
    def has_extra_workers():
        source_ip = request.remote_addr
        if is_access_allowed_other_node(source_ip):
            if EndpointNode.num_of_workers < EndpointNode.max_num_of_workers:
                EndpointNode.max_num_of_workers -= 1
                return "True"

            return "False"

    # Endpoint accessed in the setup script to set the current node & other node IPs,
    # and the security group and keypair name for launching new workers
    @app.route('/setNodeData', methods=['PUT'])
    def set_node_data():
        EndpointNode.my_ip = request.args.get('myIP')
        EndpointNode.other_node_ip = request.args.get('otherIP')
        EndpointNode.sec_grp_id_for_workers = request.args.get('secGrpId')
        EndpointNode.keypair_for_workers = request.args.get('keypairName')

        # start run periodically the checking for scaling up
        check_for_scale_up_thread = threading.Thread(target=check_for_scale_up)
        check_for_scale_up_thread.start()

        return '', 204

    # Endpoint accessed by the other node to add a new worker ip created by it to the list of allowed workers IPs
    @app.route('/addWorkerIP', methods=['PUT'])
    def add_worker_ip():
        source_ip = request.remote_addr
        if is_access_allowed_other_node(source_ip):
            new_worker_ip = request.args.get('newWorkerIP')
            EndpointNode.allowed_workers_ip.append(new_worker_ip)

            return '', 204

    # Endpoint for scaling down and terminate an Idle worker for 10 minutes
    @app.route('/scaleDown', methods=['POST'])
    def scale_down():
        source_ip = request.remote_addr
        if is_access_allowed_workers(source_ip):
            worker_instance_id = request.args.get('workerInstanceID')
            EndpointNode.ec2_client.terminate_instances(InstanceIds=[worker_instance_id])
            EndpointNode.num_of_workers -= 1

            return '', 204


def check_for_scale_up():
    while True:
        if len(EndpointNode.work_queue) > 0 and time.time() - float(EndpointNode.work_queue[0]['work_id']) > 15:
            if EndpointNode.num_of_workers < EndpointNode.max_num_of_workers:
                scale_up()
            else:
                url = f'http://{EndpointNode.other_node_ip}:5000/hasExtraWorkers'
                if bool(requests.get(url).text):
                    EndpointNode.max_num_of_workers += 1
                    scale_up()

        # Each worker checks for new work items every 5 seconds,
        # so the checking for scaling up will be every 15 seconds.
        # For example: When there at least two work items in the queue,
        # if another new worker will be launched before an existing worker
        # will process the two work items in the queue,
        # the new worker will just be launched for no reason because until it will be launched completely
        # the second work item will be processed by the first existing worker anyway.
        time.sleep(15)


def scale_up():
    sec_grp_id = EndpointNode.sec_grp_id_for_workers
    keypair = EndpointNode.keypair_for_workers
    client = EndpointNode.ec2_client

    # Launch an EC2 instance as a new worker
    launching_response = client.run_instances(
        ImageId='ami-01dd271720c1ba44f',
        InstanceType='t2.micro',
        SecurityGroupIds=[sec_grp_id],
        MinCount=1,
        MaxCount=1,
        KeyName=keypair
    )

    new_worker_id = launching_response['Instances'][0]['InstanceId']
    waiter = client.get_waiter('instance_status_ok')
    waiter.wait(InstanceIds=[new_worker_id])

    EndpointNode.num_of_workers += 1

    new_worker_response = client.describe_instances(InstanceIds=[new_worker_id])
    new_worker_ip = new_worker_response['Reservations'][0]['Instances'][0]['PublicIpAddress']

    # Establish SSH connection
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(hostname=new_worker_ip, username='ubuntu', key_filename=keypair + '.pem')

    # Transfer the setup script setupWorker.sh and the program worker.py to the new worker
    sftp_client = ssh_client.open_sftp()
    sftp_client.put('setupWorker.sh', '/home/ubuntu/setupWorker.sh')
    sftp_client.put('worker.py', '/home/ubuntu/worker.py')

    # Wait until the files are properly transferred
    while 'setupWorker.sh' not in sftp_client.listdir('/home/ubuntu/'):
        time.sleep(1)
    sftp_client.close()

    _, stdout, _ = ssh_client.exec_command('bash setupWorker.sh')

    # Wait for the script to fully complete installations and start the Flask server
    time.sleep(30)

    EndpointNode.allowed_workers_ip.append(new_worker_ip)
    url = f'http://{EndpointNode.other_node_ip}:5000/addWorkerIP'
    params = {'newWorkerIP': new_worker_ip}
    requests.put(url, params=params)

    url = f'http://{new_worker_ip}:5000/runWorker'
    params = {'myInstanceID': new_worker_id, 'creatorIP': EndpointNode.my_ip, 'otherNodeIP': EndpointNode.other_node_ip}
    requests.put(url, params=params)

    ssh_client.close()


# Allow requests from only the other endpoint node
def is_access_allowed_other_node(ip):
    if ip != EndpointNode.other_node_ip:
        abort(403, "Access denied. Your IP address is not allowed.")
    else:
        return True


# Allow requests from only workers
def is_access_allowed_workers(ip):
    if ip not in EndpointNode.allowed_workers_ip:
        abort(403, "Access denied. Your IP address is not allowed.")
    else:
        return True


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
