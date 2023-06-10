from flask import Flask, request
import hashlib
import base64
import pickle
import sys

# Would be used if the HTTP communication between the main instance and the worker worked successfully.
app = Flask(__name__)


# The method for executing if the remote python execution would work from the main instance.
def enqueue_task(data, iterations):
    data_bytes = bytes(data, encoding='utf-8')
    iterations_int = int(iterations)
    output = hashlib.sha512(data_bytes).digest()
    for _ in range(iterations_int - 1):
        output = hashlib.sha512(output).digest()

    return output


# The HTTP endpoint that would be used
# if the HTTP communication between the main instance and the worker worked successfully.
@app.route('/enqueueWorker', methods=['PUT'])
def enqueue_task():
    data = bytes(request.data)
    iterations = int(request.args.get('iterations'))
    output = hashlib.sha512(data).digest()
    for _ in range(iterations - 1):
        output = hashlib.sha512(output).digest()

    return output


# The method for executing if the remote python execution would work from the main instance,
# it gets the list of completed work serialized and deserializes it for taking the last 'top' elements from it.
def pull_task(completed_tasks, top):
    decoded_list = base64.b64decode(completed_tasks)
    deserialized_list = pickle.loads(decoded_list)
    output = ""
    top_int = int(top)

    while len(deserialized_list) > 0 and top_int > 0:
        (work_id, value) = deserialized_list.pop()
        output += "work_id: " + work_id + ", value: " + value + "\n"

    return output


# Would be used if the HTTP communication between the main instance and the worker worked successfully.
# In addition, it would be required to run the command "nohup flask run --host 0.0.0.0 &>/dev/null &"
# on each worker instance who runs that python program to keep the worker
# running as a flask server and receive HTTP requests
# also when we're not connected to the worker by SSH.
if __name__ == '__main__':
    # Get command-line arguments
    method_name = sys.argv[0]
    arg1 = sys.argv[1]
    arg2 = sys.argv[2]

    # Execute the specified method
    if method_name == 'enqueue_task':
        output = enqueue_task(arg1, arg2)
    elif method_name == 'pull_task':
        output = pull_task(arg1, arg2)
