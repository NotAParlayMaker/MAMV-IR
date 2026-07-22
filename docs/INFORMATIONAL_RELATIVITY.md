# Informational Relativity

## Definition
Informational Relativity is the technical rule that a verification status is valid only in its recorded informational frame: context, observer authority, evidence scope, method, criteria, artifact versions, policy, assumptions, and time. It does not assert that all interpretations are equally good or that observers create facts.

## Context, scope, and authority
Contexts identify the goal and source/artifact information. Claims may be local, execution, artifact, run, environment, temporal, or general in scope. The authority matrix remains the enforcement point: a sandbox establishes runtime observations, a test runner establishes configured test results for an artifact, and a static analyzer establishes only its configured analysis. A reasoning model may propose interpretations but cannot author observed runtime evidence.

## Artifacts and temporal validity
Artifact references identify a version and content hash. Evidence carries optional artifact, environment, method, frame, scope, and validity fields. A frame derivation is conservative: changed artifact, criterion, policy, context, or evidence scope requires re-verification. Historical results are retained rather than overwritten, and callers can identify stale or superseded results.

## Transformations and comparisons
`derive_frame` records a parent frame and `FrameTransformation`; it defaults to re-verification for changed fields. Cross-frame comparisons classify scope-distinct claims separately from contradictions. Perspectives can be compatible, conflicting, or incomparable; agreement is never substituted for authorized evidence.

## Completion, metacognition, and constitutional review
A `CompletionDecision` cites one frame and means that required criteria were satisfied in that recorded frame. Receipt language explicitly disclaims context-free or universal truth. Metacognitive summaries remain model inferences, not observations; constitutional review and policy approval still gate completion.

## Serialization and migration
Runs serialize frames, transformations, relative verifications, perspectives, and completion decisions. Loading old records creates a clearly labelled `legacy_inferred` frame with a limitation; legacy event hashes are preserved and are not recomputed.

## Security limitations
The SHA-256 event chain detects changes to hashed local records, including frame data, but does not supply external timestamping, independent authenticity, complete testing, security proof, or universal correctness.

## Example
A test runner can record a supported `tests_pass` result in a frame bound to code hash A and a test environment. After code hash B is registered, that result remains historical but does not silently support B; derive a new frame and run verification again.
