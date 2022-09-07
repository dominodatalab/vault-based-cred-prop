export PATH=$PATH:./bin/
export platform_namespace="${platform_namespace:-domino-platform}"
export compute_namespace="${compute_namespace:-domino-compute}"
#User credentials for  vault-user-sw
export AWS_ACCESS_KEY_ID=$(cat ./aws_creds/creds.json | jq -r '.AccessKeyId')
export AWS_SECRET_ACCESS_KEY=$(cat ./aws_creds/creds.json | jq -r '.SecretAccessKey')

echo $AWS_ACCESS_KEY_ID

export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
export VAULT_TOKEN="${VAULT_TOKEN:-faketoken}" #This token expires in 6 hours
export VAULT_NS="${VAULT_NS:-}" #This token expires in 6 hours

if [ -z "$VAULT_NAMESPACE" ]
then
      echo "\$Open Source version INSTALL No Namespaces"
else
      echo "\$Enterprise version INSTALL Create Namespace"
      vault namespace delete -namespace=admin $VAULT_NS
      vault namespace create -namespace=admin $VAULT_NS
fi
echo $VAULT_NAMESPACE

rm -rf ./root/etc/vault
mkdir ./root/etc/vault

#Generate a app token to allow Domino to communicate with Vault
vault policy write domino ./vault_policies/domino.hcl
export VAULT_TOKEN=$(vault token create -orphan -policy=domino -period=768h  -ttl 768h -format=json | jq .auth.client_token | sed 's/"//g' )

echo "About to write token to secrets and folder"
echo $VAULT_TOKEN > ./root/etc/vault/token
#We will use on these secrets engine. But there are many more (https://www.vaultproject.io/docs/secrets)
vault secrets enable aws
vault secrets enable kv

vault write aws/config/root \
    access_key=$AWS_ACCESS_KEY_ID \
    secret_key=$AWS_SECRET_ACCESS_KEY \
    region=us-west-2
#Immediately rotate them. Now only vault knows the secret key. The existing ones are replace
echo $AWS_ACCESS_KEY_ID
#echo $AWS_SECRET_ACCESS_KEY
echo "sleep for 10 seconds to allow the tokens to propagate to vault"

sleep 10

vault write -f aws/config/rotate-root

#All AWS credentials will have a lease of 1 hour and can be renewed. Max lease duration is 24 h
vault write -namespace=$VAULT_NAMESPACE aws/config/lease lease=15m lease_max=24h


