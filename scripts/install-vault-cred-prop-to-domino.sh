export docker_version=${docker_version:-latest}
export image="${image:-quay.io/domino/vault-creds-prop}"
export platform_namespace="${platform_namespace:-domino-platform}"
export compute_namespace="${compute_namespace:-domino-compute}"
export VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
export VAULT_TOKEN="${VAULT_TOKEN:-faketoken}"
export VAULT_NAMESPACE="${VAULT_NAMESPACE:-}" #admin/dominoaws

#Create the secret with the Vault Token
kubectl delete secret vault-token -n $compute_namespace
kubectl create secret generic vault-token --from-literal=token=$VAULT_TOKEN -n $compute_namespace

#Create the configmap with configurations for the side-car
echo $compute_namespace
export DOMSED_VAULT_CONFIGMAP_NAME=dynamic-aws-creds-config
kubectl delete configmap ${DOMSED_VAULT_CONFIGMAP_NAME} -n $compute_namespace
cat <<EOF | kubectl create  -n ${compute_namespace} -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: ${DOMSED_VAULT_CONFIGMAP_NAME}
data:
  dynamic-aws-creds-config: |-
    {
      "vault_endpoint": "${VAULT_ADDR}",
      "vault_namespace" : "${VAULT_NAMESPACE}",
      "polling_interval_in_seconds" : 300,
      "refresh_threshold_in_seconds" : 600,
      "lease_increment" : 30,
      "default_user" : "default"
    }
EOF

#Deploy the DOMSED Mutation to perform AWS Credential Propagation using Dynamic Secrets
kubectl delete mutation app-cloud-creds-mutation -n $platform_namespace

cat <<EOF | kubectl create -n ${platform_namespace} -f -
apiVersion: apps.dominodatalab.com/v1alpha1
kind: Mutation
metadata:
  name: app-cloud-creds-mutation
rules:
  - # Optional. List of hardware tier ids
    #hardwareTierIdSelector: []
    # Optional. List of organization names
    #organizationSelector: []
    # Optional. List of user names
    # Insert volume mount into specific containers
    labelSelectors:
    - "dominodatalab.com/workload-type=App"
    # Insert arbitrary container into matching Pod.
    insertContainer:
      # 'app' or 'init'
      containerType: app
      # List of label selectors.
      # ALL must match.
      # Supportes equality and set-based matching
      # Arbitrary object
      spec:
        name: z-vault-cloud-creds
        image: ${image}:${docker_version}
        args: ['/','5010' ]
        volumeMounts:
          - name: log-volume
            mountPath: /var/log/
          - mountPath: /var/vault/
            name: token
          - name: dynamic-aws-creds-config
            mountPath: /var/config/
            readOnly: true
    insertVolumes:
      - emptyDir: { }
        name: log-volume
      - name: token
        secret:
          secretName: vault-token
      - name: dynamic-aws-creds-config
        configMap:
          name: dynamic-aws-creds-config
EOF