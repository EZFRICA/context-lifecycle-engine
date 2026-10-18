## 3. Three-stage build (`cle/build`)
- **Resolve**: every `#ref` exists and re-hashes, or the build fails in
  milliseconds having written nothing. *Invariant 3.*
- **Replay-validate** (§4), retrospective proof over the user's own past.
- **Assemble**: compile the prompt in declared order, freeze the probe set and
  `model_fingerprint`, hash into an `Image`. Same source + components +
  substrate ⇒ same image hash. *Invariant 6.*
- **Substrate choice**: `cle build --model-id`: live Gemini (temperature 0), a
  named real model, or `stub-*` (deterministic offline).
