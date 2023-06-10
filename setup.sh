#!/bin/bash

KEY_NAME="cloud-computing-ex2-$(date +'%N')"
KEY_PEM="$KEY_NAME.pem"
SEC_GRP_MAIN="sec-grp-for-main-nodes"
SEC_GRP_WORKERS_1="sec-grp-for-workers-node1"
SEC_GRP_WORKERS_2="sec-grp-for-workers-node2"
AMI_ID="ami-01dd271720c1ba44f"
INSTANCE_TYPE="t2.micro"

# Retrieve the credentials
credentials=$(aws sts get-session-token --query 'Credentials.[AccessKeyId, SecretAccessKey, SessionToken]' --output text)

# Extract the credentials from the response
access_key=$(echo "$credentials" | awk '{print $1}')
secret_key=$(echo "$credentials" | awk '{print $2}')
session_token=$(echo "$credentials" | awk '{print $3}')

# Creating key pair and securing it
echo "Creating key pair $KEY_PEM to create and connect to new instances and saving locally."
aws ec2 create-key-pair --key-name $KEY_NAME --query 'KeyMaterial' --output text > $KEY_PEM
chmod 400 $KEY_PEM

# Creating security group for main instances
echo "Creating security group $SEC_GRP_MAIN for the main endpoint nodes:"
aws ec2 create-security-group --group-name $SEC_GRP_MAIN --description "Access main endpoint nodes"

# Getting my public IP address
MY_IP=$(curl ipinfo.io/ip)
echo "My IP address is: $MY_IP"

echo
echo "----------------------------------------------------------------------------------------------------"
echo

# Setting up firewall rules
echo "Setting up the main nodes' firewall rules for SSH from my IP only and HTTP access for all addresses:"
aws ec2 authorize-security-group-ingress --group-name $SEC_GRP_MAIN --port 22 --protocol tcp --cidr $MY_IP/32
aws ec2 authorize-security-group-ingress --group-name $SEC_GRP_MAIN --port 5000 --protocol tcp --cidr 0.0.0.0/0

echo
echo "----------------------------------------------------------------------------------------------------"
echo

# Launching the first EC2 main instance
echo "Launching the first EC2 main endpoint node:"

FIRST_MAIN_NODE_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --instance-type $INSTANCE_TYPE \
    --key-name $KEY_NAME \
    --security-groups $SEC_GRP_MAIN \
    --query 'Instances[0].InstanceId' \
    --output text)

# Wait for the instance to be running and in status OK, ready to receive SSH connections
while [[ "$(aws ec2 describe-instance-status --instance-ids $FIRST_MAIN_NODE_ID --query 'InstanceStatuses[0].InstanceStatus.Status' --output text)" != "ok" ]]; do
  sleep 5
done

# Getting the public IP address of the new instance
FIRST_MAIN_NODE_IP=$(aws ec2 describe-instances --instance-ids $FIRST_MAIN_NODE_ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo "The first endpoint node $FIRST_MAIN_NODE_ID @ $FIRST_MAIN_NODE_IP was created!"

echo
echo "----------------------------------------------------------------------------------------------------"
echo

# Deploying the Flask app to the instance (and additionally the worker app, setup workers script and keypair file so the main instances will create workers with the same keypair and deploy to them the worker app):
echo "Deploying Flask app to the first main instance, and setting up production environment (ignore the additional output):"
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" endpointNode.py ubuntu@$FIRST_MAIN_NODE_IP:/home/ubuntu/
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" worker.py ubuntu@$FIRST_MAIN_NODE_IP:/home/ubuntu/
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" setupWorker.sh ubuntu@$FIRST_MAIN_NODE_IP:/home/ubuntu/
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" $KEY_PEM ubuntu@$FIRST_MAIN_NODE_IP:/home/ubuntu/
ssh -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=10" ubuntu@$FIRST_MAIN_NODE_IP <<EOF
    chmod 400 $KEY_PEM
    sudo apt update
    # configuring in the remote instance the AWS connected account
    sudo apt install awscli -y
    aws configure set aws_access_key_id "$access_key"
    aws configure set aws_secret_access_key "$secret_key"
    aws configure set aws_session_token "$session_token"
    # installing flask and other required python packages
    sudo apt install python3-flask -y
    sudo apt install python3-pip -y
    pip install --upgrade pip
    pip install boto3
    pip install paramiko
    # running the app
    nohup python3 endpointNode.py >/dev/null 2>&1 &
    exit
EOF

echo
echo "----------------------------------------------------------------------------------------------------"
echo

# Launching the second EC2 main instance
echo "Launching the second EC2 main endpoint node:"

SECOND_MAIN_NODE_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --instance-type $INSTANCE_TYPE \
    --key-name $KEY_NAME \
    --security-groups $SEC_GRP_MAIN \
    --query 'Instances[0].InstanceId' \
    --output text)

# Wait for the instance to be running and in status OK, ready to receive SSH connections
while [[ "$(aws ec2 describe-instance-status --instance-ids $SECOND_MAIN_NODE_ID --query 'InstanceStatuses[0].InstanceStatus.Status' --output text)" != "ok" ]]; do
  sleep 5
done

# Getting the public IP address of the new instance
SECOND_MAIN_NODE_IP=$(aws ec2 describe-instances --instance-ids $SECOND_MAIN_NODE_ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo "New instance $SECOND_MAIN_NODE_ID @ $SECOND_MAIN_NODE_IP was created!"

echo
echo "----------------------------------------------------------------------------------------------------"
echo

# Deploying the Flask app to the instance (and additionally the worker app, setup workers script and keypair file so the main instances will create workers with the same keypair and deploy to them the worker app):
echo "Deploying Flask app to the second main instance, and setting up production environment (ignore the additional output):"
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" endpointNode.py ubuntu@$SECOND_MAIN_NODE_IP:/home/ubuntu/
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" worker.py ubuntu@$SECOND_MAIN_NODE_IP:/home/ubuntu/
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" setupWorker.sh ubuntu@$SECOND_MAIN_NODE_IP:/home/ubuntu/
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" $KEY_PEM ubuntu@$SECOND_MAIN_NODE_IP:/home/ubuntu/
ssh -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=10" ubuntu@$SECOND_MAIN_NODE_IP <<EOF
    chmod 400 $KEY_PEM
    sudo apt update
    # configuring in the remote instance the AWS connected account
    sudo apt install awscli -y
    aws configure set aws_access_key_id "$access_key"
    aws configure set aws_secret_access_key "$secret_key"
    aws configure set aws_session_token "$session_token"
    # installing flask and other required python packages
    sudo apt install python3-flask -y
    sudo apt install python3-pip -y
    pip install --upgrade pip
    pip install boto3
    pip install paramiko
    # running the app
    nohup python3 endpointNode.py >/dev/null 2>&1 &
    exit
EOF

echo
echo "----------------------------------------------------------------------------------------------------"
echo

# Creating security groups for worker instances
echo "Creating security group $SEC_GRP_WORKERS_1 for worker instances created by the first main endpoint node:"
aws ec2 create-security-group --group-name $SEC_GRP_WORKERS_1 --description "Access worker instances created by the first main endpoint node"
echo "Creating security group $SEC_GRP_WORKERS_2 for worker instances created by the second main endpoint node:"
aws ec2 create-security-group --group-name $SEC_GRP_WORKERS_2 --description "Access worker instances created by the second main endpoint node"

# Setting up firewall rules
echo "Setting up firewall rules for SSH and HTTP access from the two main endpoint nodes only:"
aws ec2 authorize-security-group-ingress --group-name $SEC_GRP_WORKERS_1 --port 22 --protocol tcp --cidr $FIRST_MAIN_NODE_IP/32
aws ec2 authorize-security-group-ingress --group-name $SEC_GRP_WORKERS_1 --port 5000 --protocol tcp --cidr $FIRST_MAIN_NODE_IP/32
aws ec2 authorize-security-group-ingress --group-name $SEC_GRP_WORKERS_2 --port 22 --protocol tcp --cidr $SECOND_MAIN_NODE_IP/32
aws ec2 authorize-security-group-ingress --group-name $SEC_GRP_WORKERS_2 --port 5000 --protocol tcp --cidr $SECOND_MAIN_NODE_IP/32

echo
echo "----------------------------------------------------------------------------------------------------"
echo

# Setting up initial data for the two main endpoint nodes: Their IP, the other node IP, 
# the security group for each node's workers and the keypair for creating new workers
echo "Setting up initial data for the two main endpoint nodes by HTTP request to a defined endpoint:"
curl -X PUT "http://$FIRST_MAIN_NODE_IP:5000/setNodeData?myIP=$FIRST_MAIN_NODE_IP&otherIP=$SECOND_MAIN_NODE_IP&secGrpId=$SEC_GRP_WORKERS_1&keypairName=$KEY_NAME"
curl -X PUT "http://$SECOND_MAIN_NODE_IP:5000/setNodeData?myIP=$SECOND_MAIN_NODE_IP&otherIP=$FIRST_MAIN_NODE_IP&secGrpId=$SEC_GRP_WORKERS_2&keypairName=$KEY_NAME"

echo
echo "----------------------------------------------------------------------------------------------------"
echo

echo "Setup script completed!"
echo "If no errors occurred during the script execution, you can now send HTTP requests to the main endpoints with the IP addresses $FIRST_MAIN_NODE_IP or $SECOND_MAIN_NODE_IP:"
echo "Send PUT /enqueue?iterations=num with the body containing the actual data, or POST /pullCompleted?top=num that will return the latest completed work items."