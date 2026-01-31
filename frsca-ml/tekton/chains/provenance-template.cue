// FRSCA-ML CUE Template for Tekton Chains
// This template maps TaskRun results to the custom ML Training Predicate.

import "encoding/json"

// Input: The TaskRun object is injected by Chains
taskRun: _

// Output: The in-toto statement (or just the predicate, depending on Chains config)
// Here we define the predicate structure to be merged into the attestation.

predicateType: "https://frsca.dev/provenance/ml-training/v0.2"
predicate: {
    buildDefinition: {
        buildType: "https://frsca.dev/buildtypes/ml-training/v1"
        externalParameters: {
            // Mapping parameters from the TaskRun
            for p in taskRun.spec.params {
                "\(p.name)": p.value
            }
        }
    }
    runDetails: {
        builder: {
            id: "https://frsca.dev/builders/tekton-chains" // Placeholder
        }
        metadata: {
            startedOn: taskRun.status.startTime
            finishedOn: taskRun.status.completionTime
        }
    }
    mlSpecifics: {
        // Parse JSON results from the task
        // We look for specific result names defined in our Task

        let metrics_result = [for r in taskRun.status.taskResults if r.name == "TRAINING_METRICS" { r.value }]
        if len(metrics_result) > 0 {
            metrics: json.Unmarshal(metrics_result[0])
        }

        let hyperparams_param = [for p in taskRun.spec.params if p.name == "hyperparameters" { p.value }]
        if len(hyperparams_param) > 0 {
            // Assuming hyperparameters are passed as a JSON string
            hyperparameters: json.Unmarshal(hyperparams_param[0])
        }

        // Environment details could be extracted from annotations or results
        environment: {
            framework: "pytorch" // Simplified for template
        }
    }
}
