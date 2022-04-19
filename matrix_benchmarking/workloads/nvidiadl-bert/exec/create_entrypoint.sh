oc create cm bert-entrypoint --from-file=run-bert-multinode_pretraining.sh,run-bert-multinode_squad.sh -oyaml --dry-run=client | oc apply -f-
