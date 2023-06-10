As I understood the exercise initially -\
the two main nodes are aware of the workers and each enqueue (and pullCompleted) requests\
are sent to the workers in HTTP requests.\
So the main nodes kept the "free" workers' IPs and keypairs for connecting to them repeatedly in SSH.\
I thought the pullCompleted task also should be made by a worker.

I tried to communicate **from** the main endpoint nodes **to** the workers in differenrt ways:
1. by transferring in sftp the worker.py program to the new workers (in their creation)\
and execute the program remotely in SSH - didn't succeed, tried only on enqueue task.
2. by an HTTP endpoint in the worker (the same method in worker.py with minor changes to make it an endpoint instead of regular method) -\
didn't succeed, tried only on enqueue task.
3. by executing a bash script - there are two scripts for enqueue task and for pull task I transferred to new workers in creation - succeed.

Because of I thought we should do the pull task remotely in the worker,\
I tried to serialize the completed work items list and send it to the workers, where I deserialized them,\
but that made some troubles, and finnaly I changed the completed work items list to a list of strings, each representing a completed work item.

The scaling up is made if there are no free workers at the moment and it's aloowed by the maximum number of workers in each node.

Also, I thought the completed work items should be synchronized between both nodes, so each completed work item is sent to the another node for updating.
