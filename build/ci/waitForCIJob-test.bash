#!/bin/bash
set -e

echo "Waiting for the test job to become ready"
echo "GitHub Run ID $TEST_INPUT"
echo $TEST_INPUT

timeout ${WAIT_DURATION:-900} bash -c "while [[ $(kubectl get job -l ci-run=$TEST_INPUT,test-name=${TEST_NAME:-pytest} -o json | jq -r '.items[0].status.succeeded') != 1 ]]; do sleep 5; done"

echo "Job is complete"