export platform_namespace="${platform_namespace:-domino-platform}"
export compute_namespace="${compute_namespace:-domino-compute}"
export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
export VAULT_TOKEN=$(cat ./root/etc/vault/token)
export VAULT_NAMESPACE="${VAULT_NAMESPACE:-}" #admin/dominoaws
export PATH=$PATH:./bin/
export VAULT_TOKEN=$(vault token create -orphan -policy=domino -period=768h  -ttl 768h -format=json | jq .auth.client_token | sed 's/"//g' )
echo $VAULT_TOKEN > ./root/etc/vault/token
echo $VAULT_TOKEN
kubectl delete secret vault-token -n $compute_namespace
kubectl create secret generic vault-token --from-literal=token=$VAULT_TOKEN -n $compute_namespace
