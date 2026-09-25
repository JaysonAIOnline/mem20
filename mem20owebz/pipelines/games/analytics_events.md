# Analytics Event Dictionary

Optional. Design events **before** code.

| event | when | props |
|-------|------|--------|
| session_start | boot | platform, version |
| tutorial_step | each beat | step_id |
| run_end | fail/win | duration, cause |
| economy_sink | spend | item, amount |
| economy_source | gain | item, amount |

No PII. Vertical slice can log to local JSON. Cloud analytics is post-ship.
