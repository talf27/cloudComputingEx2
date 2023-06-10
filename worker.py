from flask import Flask, request
import time
import threading
import requests
import hashlib

app = Flask(__name__)


class Worker:
    my_instance_id = None
    creator_node_ip = None
    endpoint_nodes_ip = []

    # Endpoint accessed by the creator main node to start the worker lifetime and set another data for the worker
    @app.route('/runWorker', methods=['PUT'])
    def run_worker():
        Worker.my_instance_id = request.args.get('myInstanceID')
        Worker.creator_node_ip = request.args.get('creatorIP')
        Worker.endpoint_nodes = [Worker.creator_node_ip, request.args.get('otherNodeIP')]

        get_work_thread = threading.Thread(target=get_work)
        get_work_thread.start()

        return '', 204


def get_work():
    last_work_time = time.time()

    while time.time() - last_work_time <= 600:
        for i in range(len(Worker.endpoint_nodes)):
            current_node_ip = Worker.endpoint_nodes[i]
            try:
                url = f'http://{current_node_ip}:5000/getWorkItem'
                get_work_response = requests.get(url)
                if get_work_response.status_code == 200:
                    response_content = get_work_response.json()
                    work_id = response_content['work_id']
                    data = response_content['data']
                    iterations = response_content['iterations']
                    hashed_value = do_work(data, iterations)
                    url = f'http://{current_node_ip}:5000/updateCompletedWork'
                    params = {'work_id': work_id, 'value': hashed_value}
                    requests.put(url, params=params)
                    last_work_time = time.time()
            except:
                continue

        time.sleep(5)

    # if worker doesn't get new work item for 10 minutes (600 seconds), it will inform to terminate it.
    url = f'http://{Worker.creator_node_ip}:5000/scaleDown'
    params = {'workerInstanceID': Worker.my_instance_id}
    requests.post(url, params=params)


def do_work(data_str, iterations_str):
    try:
        data = bytes(data_str, encoding='utf-8')
        iterations = int(iterations_str)

        output = hashlib.sha512(data).digest()
        for _ in range(iterations - 1):
            output = hashlib.sha512(output).digest()

        return str(output)
    except:
        return "Work got invalid parameters."


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
