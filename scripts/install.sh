#!/bin/bash
set -e
pip3 install -r requirements.txt
#Create side-car container docker image and push to registry
export sidecar_image_tag=${sidecar_image_tag:-latest}

./scripts/create_and_push_docker_image.sh $sidecar_image_tag


export platform_namespace="${platform_namespace:-domino-platform}"
export compute_namespace="${compute_namespace:-domino-compute}"
export PATH=$PATH:./bin/
export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
export VAULT_TOKEN="${VAULT_TOKEN:-faketoken}"
export VAULT_NS="${VAULT_NS:-}" #admin/dominoaws
if [ -z "$VAULT_NS" ]
then
      echo "\$Open Source version INSTALL No Namespaces"
else
      export VAULT_NAMESPACE="admin/${VAULT_NS}"
      echo "\$Enterprise version INSTALL Create Namespace"
      vault namespace delete -namespace=admin $VAULT_NS
      vault namespace create -namespace=admin $VAULT_NS
fi
echo $VAULT_NAMESPACE
#Use default profile with admin privileges to configure aws user, demo bucket and demo policies and roles
#export AWS_ACCESS_KEY_ID=
#export AWS_SECRET_ACCESS_KEY=

#Create a bucket and sub-folders
python ./src/admin/create_demo_customer_bucket.py

echo 'Run configure_vault_aws_user.py'
#Configure vault with aws iam user
python ./src/admin/configure_vault_aws_user.py

echo 'Run configure_ldap_based_aws_policies_and_roles.py'
#Configure Sample Policies and Roles in AWS
python ./src/admin/configure_ldap_based_aws_policies_and_roles.py


echo 'configure vault'
#Configure Vault
./scripts/configure-vault.sh

#Configure K8s cluster
./scripts/install-vault-cred-prop-to-domino.sh $docker_version

echo 'Run configure_vault_aws_roles.py'
#Configure roles in Vault
python src/admin/configure_vault_aws_roles.py