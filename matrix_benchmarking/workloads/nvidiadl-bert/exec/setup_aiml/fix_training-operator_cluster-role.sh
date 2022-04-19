PATCH='{
  "rules": [
    {
      "apiGroups": [
        "kubeflow.org"
      ],
      "resources": [
        "tfjobs",
        "mxjobs",
        "pytorchjobs",
        "xgboostjobs",
        "tfjobs/status",
        "pytorchjobs/status",
        "mxjobs/status",
        "xgboostjobs/status",
        "tfjobs/finalizers",
        "pytorchjobs/finalizers",
        "mxjobs/finalizers",
        "xgboostjobs/finalizers"
      ],
      "verbs": [
        "create",
        "delete",
        "get",
        "list",
        "patch",
        "update",
        "watch"
      ]
    },
    {
      "apiGroups": [
        ""
      ],
      "resources": [
        "pods",
        "services",
        "endpoints",
        "events"
      ],
      "verbs": [
        "*"
      ]
    },
    {
      "apiGroups": [
        "apps",
        "extensions"
      ],
      "resources": [
        "deployments"
      ],
      "verbs": [
        "*"
      ]
    },
    {
      "apiGroups": [
        "scheduling.volcano.sh"
      ],
      "resources": [
        "podgroups"
      ],
      "verbs": [
        "*"
      ]
    }
  ]
}'

oc patch clusterroles/training-operator --patch "$PATCH" --type=merge
