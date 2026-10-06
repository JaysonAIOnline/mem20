# mem20dreamz

The dream engine. Iteration must **improve**, never **condense**.

## The defect this replaces

`cog/braid_dream_section.py:115` did `st["seed"] = out[:300]`. Every iteration
read a 300-character tail of the previous output, so early structure could not
survive and each pass was a resample rather than a revision. Measured on a real
run before the fix, the artifact oscillated `273 -> 993 -> 246 -> 11625` -
regeneration with a lottery. A lineage now keeps the artifact in full, every
intermediate version, an invention register, and its own evolving config.

## Panel: one model per member

The owner's rule. A single-model panel makes its blind spot *systematic*: every
member can be confidently wrong the same way, and agreement is laundered into
consensus. Eight distinct models, every one verified to answer on this host by a
real call. `assert_roster_valid()` **raises** on a duplicate model - it used to
deduplicate silently, which quietly deleted the `systems_inventor` role and left
the invention register permanently empty with nothing reporting why.

Only Cohere and Groq serve a completion today. A provider's catalog is not
evidence of callability: NVIDIA returns 82 model ids and answers none of them.
See `EXCLUDED_PROVIDERS` in `panel.py` for what was tried and why each failed.

**Funding is resolved through `llm.env_value`, never `os.environ`.** It used to
read the environment directly, which worked only by accident: `llm` published the
entire secrets file into the process environment at import time, so
`COHERE_API_KEY` and `GROQ_API_KEY` happened to be sitting there. When that leak
was closed — it was handing every process that imported `llm` the control-plane
admin password, the sudo password and every cloud key in the estate — the panel
quietly reported *no funded members* and `panel()` returned an empty list. Nothing
raised and nothing was logged. A panel whose whole purpose is noticing it has lost
a member must never be the thing that loses it silently, so the resolution lives
in one place and there are tests for both directions: funded resolves, unfunded
reports unfunded.

## The iteration

1. Load lineage - artifact, changelog, invention register, dreamer config.
2. Assemble context - the full lineage as a digest fitted to each panelist's
   window, plus the artifact verbatim. Never a truncated tail.
3. Panel critiques, each member in its own domain.
4. Omission of the current state - the "what was never asked for" list that
   drives revision. Used as input, *not* as the recorded score.
5. The skeptic, a standing role, recorded even when overruled.
6. Three forecasts - monetary, estate, human - rubrics fixed at seed time.
7. Invention, spawned from what the panel actually found.
8. The dreamer evolves - techniques and guidance, per lineage, never global.
9. Generate N candidates, **each by a different model**.
10. Score every candidate on both axes, judged by models that wrote none of them.
11. Select: fidelity floor, never-condenses invariant, omission veto, then a
    blind A/B against the incumbent. Only a candidate that WINS is adopted, so
    the artifact can never regress.

## Invariants, enforced not requested

Rebuilt 2026-09-30. Three invariants were **removed** and one metric replaced
them, because together they made this engine a polisher: a candidate had to
resemble the brief, be no shorter than its predecessor, and beat the incumbent
head to head. An engine with no legal way to become something else cannot
produce the unprecedented, however it is seeded.

*Removed:*

* **Never condenses** - a revision under 60% of its predecessor was rejected.
* **Fidelity floor** - below 70 the revision was rejected however good it read.
* **No regression** - adoption required winning a blind comparison. Measured
  against the pre-rebuild code, this is the guard that mattered: a genuinely
  alien candidate is the *least* likely to win a head-to-head, so the old
  engine reliably kept the incumbent and could not be reborn by surprise.

*Replaced by divergence.* The research on dreaming says the mechanism is
associative divergence - sleep onset binds recent experience to *loosely
associated* memory, and semantic distance predicts creative quality (Lacaux et
al. 2021; Horowitz et al. 2023). So a candidate is now measured by how far it
travels from the incumbent rather than how closely it tracks it, in pure
arithmetic with no model in the loop, so no panelist can talk it into a score.
`DIVERGENCE_FLOOR` excludes paraphrase; `GENESIS_DISTANCE` marks a candidate
that has travelled so far it is not a revision at all.

*The genesis path.* At or above `GENESIS_DISTANCE` a candidate may supersede
the lineage outright. The prior artifact is kept in `lineage.superseded` and in
the braid chain rather than discarded, so a supersession stays auditable
instead of looking like the lineage always was this.

*Kept, because they are about honesty rather than novelty:*

* **Omission veto** - if the panel found nothing genuinely new, the iteration did
  no work and fails. This is the one guard that *demands* novelty.
* **No funding, no dream** - the engine refuses rather than faking output.
* **audit-hollow** - finds iterations that were failed calls, so a provider
  error can never be mistaken later for a dream that happened.
* Braid provenance - every adopted iteration is committed and re-proved.

The blind comparison still runs and is still recorded, as `evidence_only` in the
selection record. It no longer vetoes.

## Seeding: cues, not tasks

There is no pool of sentences. The previous seeder held twelve hardcoded
sentences and handed them out round-robin; the attempt after that derived
sentences from the estate's *backlog*, which is a ticket queue wearing a
dream's clothes and inverted the engine's purpose, since a board should be fed
by dreams.

A cue is now a **theme paired with something it never keeps**, built from the
estate's own language: the words that a handful of unrelated packages share in
their descriptions, with template filtered out (a phrase a dozen crew runtimes
copied is not a domain word, and a filename is not a theme). On this box that
is 262 shared words and ~33,600 distinct cues, none of which repeats, and none
of which is an instruction. `SeedExhausted` is raised rather than repeating one.


## Judging honestly

A panel cannot reliably grade its own output on a self-reported 0-100, so
selection uses a **blind pairwise comparison** with a randomised order, judged by
the strongest model that wrote neither artifact. That matters more than it
sounds: routing the contest to a 7B model froze the dream at iteration 3, with
the incumbent winning every round regardless of candidate quality. A judge that
cannot tell two artifacts apart returns "incumbent stands" every time, which
looks like convergence and is actually blindness.

## Subsystem awareness

`estate.py` reports what is *measured*, not remembered: real installable packages
on disk, the toolchest inventory's tool counts, and the capability claims braid
holds. The interesting column is the gap between them.

A claim whose name does not match an installed package is reported as
**unverified, not absent** — the join is by name only, and `mem20cviz` versus
`cap.cv-inference.v1` may be the same thing spelled differently. Overstating that
gap would feed the panel a falsehood, which is worse than admitting the join is
fuzzy. Claims that are plainly probe noise (one- and two-letter ids) are called
out separately.

The feed goes to the inventor, because an inventor that does not know what exists
reinvents the tool already sitting two directories away. It explicitly does *not*
suppress proposals of nonexistent capabilities; that is the whole point.

## Idle dreaming

`idle.py` plus `mem20dream-idle.timer` (every 20 minutes, `Type=oneshot`,
`Restart=on-failure`) produce prototypes, proposals and ideas. Five iterations per
turn, which measures at roughly six minutes and leaves headroom inside the tick.

**An active run always wins.** `mem20-dream run` takes a lock for the whole run and
idle dreaming skips its turn entirely while it is held — no tokens spent, no write.
A lock older than `MEM20DREAM_LOCK_STALE_S` stops counting, so a crashed run cannot
wedge idle dreaming for ever.

Alerts use a different bar per dream type, because a one-iteration idle idea and a
long refinement are not comparable:

- **idle** alerts on *novelty* (omission ≥ 55, or 3+ inventions) — it may interrupt you
- **active runs** need 3+ iterations, fidelity held in ≥80% of them, *and* a still-growing artifact

Growth alone is not enough: a run that abandoned the brief does not alert. A push
that failed is reported as `delivered: false` with the reason, never as sent.

## Promotion

`mem20-dream promote` writes a portable roadmap pack — maps, skills, information,
design — as markdown plus JSON, one directory per dream so many dreams share a
store. It refuses on a damaged chain **and** on a hollow lineage, because a valid
signature proves the bytes are intact, not that a dream happened.

Skills are labelled *learned observations*, not verified procedures: they came from
a panel critique, not from a test that passed. Scores are labelled panel judgements,
not measurements. The pack leads with what it is not.

### A failed promotion rolls back

Each file is written atomically, but the *pair* used to be written in place with no
recovery, and the overwrite guard only asked whether the target directory had
anything in it. So a crash between the two files left a non-empty target that then
refused every future retry without `--force` — and an operator could not tell a
half-written pack from a real one. Proven, not theorised: under a real
`EFBIG` (a `ulimit -f` cap) the old code left a stray `.json.tmp` behind and every
subsequent retry raised `FileExistsError`.

Now the pack is **rendered, then staged, then installed**:

* nothing touches the target until the whole pack is rendered and fsynced, so a
  renderer error fails before writing rather than halfway through;
* a staging directory is removed on any failure, so a failed promotion leaves the
  store exactly as it found it and a plain retry works;
* replacing an existing pack sets the old one aside under a `.bak` name first, so
  a failure at the install rename is recoverable — and if the rollback itself
  fails, the surviving path is named in the raised error rather than the pack
  quietly disappearing;
* a pack stranded by a process killed *between* the two renames is restored on the
  next attempt, and `promote` reports that it did.

The overwrite guard also learned to tell debris from real work, narrowly: a
directory counts as interrupted debris only when everything in it is a filename
this code would have written. A directory holding anything else is a human's, and
is refused rather than cleaned up.

## The run lock is exclusive

An active run always wins over idle dreaming — and now over *another run*. The old
`claim_active` wrote the lock unconditionally, which is enough to stop idle
dreaming from crowding out real work but does nothing about run versus run: the
second writer silently replaced the first's claim, so both dreamed at once and the
lock named whichever wrote last. Harmless when a person runs one command at a time;
not harmless the moment a button can fire two requests.

Six processes racing for one claim under the old code all returned "claimed", and
the lock remembered only the last. Under the current code exactly one wins, the
other five are refused, and each refusal names the holder.

* the lock file is created with `O_EXCL`, so the check and the claim are one step
  rather than two with a window between them;
* a claim carries an ownership token, and release only frees a lock the caller
  holds — otherwise a *refused* run would delete the incumbent's lock on its way
  out through its own cleanup;
* a stale lock is taken over only when it is stale **and** its recorded pid is
  gone. Stale is not the same as dead: a slow run is still honouring its claim, and
  stealing it would cause the collision the lock exists to prevent. An unreadable
  pid errs towards refusing.
* an unreadable or empty lock file is reported as *held by an unidentified run*
  while it is fresh, not as free.

`mem20-dream run` exits **3** when it cannot claim, deliberately distinct from 2
(paused) and 0 (finished): that run never started, and a caller can tell that from
a pause. Idle dreaming now claims the lock for the duration of its turn too, so a
run cannot start in the minutes an idle turn is working — the claim is what stops
work starting, so it has to happen first.

## Two real defects found in production

**A failed panel manufactured an iteration.** A provider outage produced
iterations with zero critiques and zero inventions: the engine stored the error
honestly but still committed the node, and 39 such lineages exist. `run_iteration`
now raises when not one panelist answered, so the caller checkpoints and pauses. A
partial result still counts — only a total wipeout aborts. `audit-hollow` finds and
marks any that predate the fix, and promotion refuses them.

**Promotion could only ever hold one dream.** The output directory was both the
store and the pack directory, so a second promotion raised on a non-empty
directory. Each dream now gets its own subdirectory.

**A run could steal another run's claim.** See "The run lock is exclusive" above.

## Run

```sh
mem20-dream panel                                  # roster, and who is excluded
mem20-dream new --seed "..." --foundation "..."     # create
mem20-dream run --dream-id <id> --iterations 5      # iterate (exit 3 = lock held)
mem20-dream show --dream-id <id>                    # full record
mem20-dream chain --dream-id <id>                   # the braid chain
mem20-dream verify --dream-id <id>                  # re-prove cold, exit 1 on damage
mem20-dream rewind --cid <cid>                      # read an iteration back from braid
mem20-dream idle                                   # one idle turn (yields to a run)
mem20-dream idle-stats                              # what idle dreaming produced
mem20-dream promote --dream-id <id> --out <dir>     # portable roadmap pack
mem20-dream promotable                              # which are promotable, and why not
mem20-dream audit-hollow [--commit]                 # failed calls, not dreams
mem20-dream list
```

Dreams are also browsable, reviewable and promotable from the control plane's
**Dreams** tab, which imports this engine as a library. See
`/opt/mem20/mem20controlz/README.md`.

Env: `MEM20DREAM_CANDIDATES` (default 3), `MEM20DREAM_WRITER_TOKENS` (16000),
`MEM20DREAM_STORE` (`/opt/mem20/store/dreams`), `MEM20DREAM_IDLE_LOCK`,
`MEM20DREAM_ESTATE_ROOT`, `MEM20DREAM_BRAID_LOG`, `MEM20DREAM_LOCK_STALE_S`,
`NTFY_TOPIC` (default `mem20`).

## Durability, stated honestly

A commit reports `ack` — proof at write time — never `proven`. That distinction is
not pedantry: braid acknowledged four dream nodes that later failed to verify. Use
`mem20-dream verify`, which re-proves every node from a cold process and exits
non-zero on any damage.

## Tests

```sh
/root/.venv/bin/python -m pytest tests -q    # 120 tests
/root/.venv/bin/ruff check .
```

Covers the never-condenses guard, duplicate-model rule, omission veto, that
selection cannot adopt a regression, lineage round-trip and digest ordering, verdict
parsing, prompt/format contract, idle fairness and pause-on-outage, the per-type
alert bars, promotion's honesty and refusal gates, hollow-iteration auditing, and
an end-to-end guard on braid's provenance gate.

Plus the two crash-consistency properties above, each with the defect proven first:
that a second claim cannot steal an active run (including that release only frees a
lock the caller owns, that a stale-but-live run is not stolen, and that the CLI
exits 3 rather than spending an iteration), and that a failed promotion leaves the
store as it found it, a retry works without `--force`, a force-replacement restores
the previous pack, a failed rollback names the surviving path, and a directory
holding an unrelated file is never treated as debris.

## Managed members (package-review integration)

Single-purpose organs grouped here by reference; they live in their own
top-level directories and are smoke-verified there (37):

- `mem20ambientteamradioz`
- `mem20autogeneratedprototypepathz`
- `mem20compoundingproductecosystemz`
- `mem20continuousimprovementloopz`
- `mem20creativetrendradarz`
- `mem20crossplatformmicrokernelz`
- `mem20dynamicphasereplannerz`
- `mem20energyawarecomputemigrationz`
- `mem20energyawarefoundationz`
- `mem20experiencefrictiondetectorz`
- `mem20faultcontainmentcellsz`
- `mem20federatedresearchgridz`
- `mem20hotswappableservicefoundationz`
- `mem20instantappsynthesisz`
- `mem20interactivecampaignbuilderz`
- `mem20loreragcontentgeneratorz`
- `mem20multichannelcommandstreamz`
- `mem20multimodalcreativedirectorz`
- `mem20multimodaldatanormalizerz`
- `mem20multimodaltaskcapturez`
- `mem20multimodalunderstandingcorez`
- `mem20offlineappdeliveryz`
- `mem20opportunityradarz`
- `mem20performanceregressionhunterz`
- `mem20presenceawarecommunicationshubz`
- `mem20prioritycollisionresolverz`
- `mem20realtimeexecutionmapz`
- `mem20realtimeteampresencez`
- `mem20realworldimpactrewardsz`
- `mem20safepatchsynthesisz`
- `mem20skillbasedprogressionbrainz`
- `mem20styleguideagentz`
- `mem20syntheticevaluatorarenaz`
- `mem20universaldatatranslatorz`
- `mem20universalhealthnervoussystemz`
- `mem20webhooksupernetworkz`
- `mem20zerodowntimemigrationbrainz`
