# cloudComputingEx2

cloud-based queue & work management system for parallel processing,\
that runs some number of SHA512 iterations of computation over data submitted by the user,\
with the following endpoints:
- **PUT** /enqueue?iterations=**num**– with the body containing the actual data (a small binary data, 16 – 256 KB), and the number of computation iterations.\
The response for this endpoint would be the id of the submitted work.
- **POST** /pullCompleted?top=**num** – returns the latest completed work items (the final value for the work and the work id).

-----

The system handles dynamically load and deliver the results as soon as possible.\
It adjusts dynamically to the actual workload on the system:\
There are two main endpoint nodes handling the enqueue and pullCompleted endpoints,\
each can create maximum 3 new workers - instances that are used to compute the data submitted by users.\
If there is a work item waiting for procession for more than 15 seconds,\
the node will scale up and create a new worker,\
and if there is an idle worker which doesn't get work items for 10 minutes,\
the system will scale down and terminate that worker instance.

The system is deployed to AWS on an EC2 instances as standard application\
written in python with Flask.

-----

after cloning the repository:
- install AWS CLI
- configure AWS setup with access keys of an existing user and **region: eu-west-1 - Europe (Ireland)**
- *cd ./cloudComputingEx2/*
- run the bash script that deploys the code to the cloud: *bash setup.sh*
- you can see the script's output example at the file "output.txt".

-----

you can send PUT & POST requests to the app's endpoints, with their IP addresses mentioned at the end of the script's execution:
- enqueue with binary data and iterations number as parameter will compute the data for the specified number of iterations.
- after that, pullCompleted with top number as parameter will give the 'top' latest completed work items computed.
- If this is the first 'enqueue' of any of the two main nodes, wait some minutes for the workers creation\
before checking the latest completed work items.

-----

A guide that explains expected failures and how to handle them in a real-world project is in the file "failuresGuide.txt".
