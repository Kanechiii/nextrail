# Evidence verification and recommendation policy

The claim ledger is a v1-compatible sidecar to the original course catalog.

Claims cover course-access cost, certificate cost, and availability separately. Each carries an official HTTPS source URL, an offset-aware timestamp, a reviewer identifier, and an explicit approval state. The ledger is not a certificate of truth: a reviewer must independently confirm each source before approving a real entry.

The evaluation engine fails closed on synthetic or unauthorized providers, nonofficial URLs, mismatched metadata, duplicate records, unapproved review states, future timestamps, and expired observations. Access and certificate price claims expire after 30 days; availability claims expire after 7 days. These are conservative development defaults, not guarantees of availability.

The recommendation engine only returns available offerings with current, approved access-cost evidence. Zero-budget recommendations require verified free course access; certificate costs remain separately reported, including paid or unknown certification. Unknown facts are never converted to free. Scores deterministically prefer free access and independently verified free or unoffered certificates. Equal scores are ordered by stable resource ID.

No live providers, source review service, persistent audit store, network fetching, or account data are introduced. Integration with the existing pathway generator is intentionally deferred until the approved evidence policy and persistence review are complete.

Run `python -m unittest discover -s scripts -p "test_*.py" -v` and `python -m compileall -q services/api/nextrail_evidence`.
