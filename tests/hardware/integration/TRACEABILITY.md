# T42 A.1–A.6 Integration Traceability

| Contract | Integration evidence |
|---|---|
| A.1 Contract | Existing domain/Port contract suites plus executable Capability schemas in the public-path validation scenario |
| A.2 Registry | `test_a1_a2_registry_queries_are_available_only_through_facade` |
| A.3 Execution | all-operation, invalid/offline and invalid-output scenarios |
| A.4 Permission | approval-blocked then human-approved scenario |
| A.5 Reliability | unknown timeout, confirmed cancel and same-key scenarios |
| A.6 Events | isolated failing subscriber, persisted UTC event and audit scenario |

All integration test bodies invoke actions through `HardwareFacade`; Driver setup and
fault injection are confined to `composition.py`.
