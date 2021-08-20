# Run DUG in minikube

Reference: https://kubernetes.io/docs/tasks/tools/install-minikube/

## Setup and start

```
minikube start --driver=virtualbox
minikube status
```

## Delete
```
minikube delete
```

## Start DUG

Create Namespace
```
kubectl create -f namespace.yaml
```

Create Storage Class
```
kubectl apply -n dug -f storageclass.yaml
```

Launch DUG
```
cd ..

# Copy the secrets template file and modify or ignore this step and random
# passwords will be set.  Check "create-dug-secret-out.log" for generated
# passwords and delete the log to keep passwords (generated or set) safe.
cp dug-secrets-template.properties dug-secrets.properties
# Edit dug-secrets.properties and change passwords.

cp dug-configmap-template.properties dug-configmap.properties
# Edit dug-configmap.properties and change values if needed.

# Ensure kubectl is configured for Kubernetes cluster.

# Execute script to create configmap in cluster.
NAMESPACE="dug" ./create-dug-configmap.sh

# Execute script to create secrets in cluster.
NAMESPACE="dug" ./create-dug-secrets.sh

# Deploy the Dug stack to Kubernetes.
kubectl apply -n dug -f stack.yaml
```

## Depoy cron job
```
kubectl apply -n dug -f ../annotate-cronjob.yaml
```

## Manually trigger cronjob
```
kubectl create job -n dug --from=cronjob/annotate annotate-manual-0710-2
```

## Port forward Dug to local
```
kubectl port-forward -n dug service/dug 5551:5551
```
